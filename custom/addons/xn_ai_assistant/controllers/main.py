# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

SESSION_HISTORY_KEY = 'xn_ai_history'

# Three exchanges. Enough for "and last year?" to work, short enough that the
# cached prefix stays small and an old misunderstanding does not follow the
# conversation around for the rest of the day.
MAX_HISTORY_TURNS = 6


class AiAssistantController(http.Controller):
    """JSON endpoints for the assistant launcher.

    auth='user' is the whole security story: each route runs in the session of
    whoever is logged in, so request.env is their environment and every tool
    the assistant calls is filtered by their own record rules. There is no
    user id in any payload and nothing here to spoof.
    """

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def _history(self):
        """Prior turns for this session.

        Held server side rather than posted by the browser. Client-supplied
        history would let a user hand the model invented assistant turns --
        which cannot grant them data, because the tools still enforce access,
        but can make the assistant appear to confirm things it never said.
        A screenshot of that is a support problem worth not having.
        """
        history = request.session.get(SESSION_HISTORY_KEY) or []
        return history if isinstance(history, list) else []

    def _remember(self, question, answer, log_id=None):
        """Store a turn.

        The assistant entry carries its log_id alongside role and content.
        ai.assistant.answer copies only role and content into the request, so
        the extra key never reaches the model -- it exists so that a
        conversation restored after a page refresh keeps working rating
        buttons rather than losing them.
        """
        history = self._history()
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer,
                        "log_id": log_id})
        request.session[SESSION_HISTORY_KEY] = history[-MAX_HISTORY_TURNS:]

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @http.route('/xn_ai/assistant/ask', type='json', auth='user')
    def ask(self, question=None, **kwargs):
        question = (question or '').strip()
        if not question:
            return {'ok': False,
                    'error': _("Please type a question first.")}

        if len(question) > 2000:
            return {'ok': False,
                    'error': _("That question is too long. Please shorten it.")}

        try:
            result = request.env['ai.assistant'].answer(
                question, history=self._history())
        except UserError as exc:
            # Refusals the asker should see: switched off, budget spent,
            # provider unreachable.
            return {'ok': False, 'error': str(exc)}
        except Exception:  # noqa: BLE001
            _logger.exception(
                "xn_ai_assistant: request failed for %s",
                request.env.user.login)
            return {'ok': False,
                    'error': _("Sorry, something went wrong on my side.")}

        answer = (result or {}).get('text') or _("Sorry, I did not understand that.")
        log_id = (result or {}).get('log_id')
        self._remember(question, answer, log_id)
        return {'ok': True, 'answer': answer, 'log_id': log_id}

    @http.route('/xn_ai/assistant/history', type='json', auth='user')
    def history(self, **kwargs):
        """The conversation so far, for redrawing the panel after a refresh.

        Without this the server remembers a conversation the panel does not
        show, and the next answer silently uses context the person cannot
        see. That is worse than having no memory at all.
        """
        ratings = {}
        log_ids = [turn.get('log_id') for turn in self._history()
                   if turn.get('log_id')]
        if log_ids:
            logs = request.env['ai.request.log'].sudo().browse(log_ids).exists()
            for log in logs:
                # Only this user's rows, in case a session outlives a login.
                if log.user_id.id == request.env.user.id:
                    ratings[log.id] = log.feedback or None

        messages = []
        for turn in self._history():
            if turn.get('role') == 'user':
                messages.append({"role": "user", "text": turn.get('content')})
            elif turn.get('role') == 'assistant':
                log_id = turn.get('log_id')
                messages.append({
                    "role": "bot",
                    "text": turn.get('content'),
                    "logId": log_id,
                    "rating": ratings.get(log_id),
                })
        return {'ok': True, 'messages': messages}

    @http.route('/xn_ai/assistant/clear', type='json', auth='user')
    def clear(self, **kwargs):
        request.session[SESSION_HISTORY_KEY] = []
        return {'ok': True}

    @http.route('/xn_ai/assistant/feedback', type='json', auth='user')
    def feedback(self, log_id=None, rating=None, comment=None, **kwargs):
        """Rate one answer.

        The log row is reached with sudo() because ordinary users have no
        write access to ai.request.log and should not be granted any. The
        ownership check below is what authorises this single write: a user
        may rate the answers they asked for, and nothing else.
        """
        if rating not in ('up', 'down'):
            return {'ok': False, 'error': _("Unknown rating.")}
        try:
            log_id = int(log_id)
        except (TypeError, ValueError):
            return {'ok': False, 'error': _("Unknown answer.")}

        log = request.env['ai.request.log'].sudo().browse(log_id).exists()
        if not log or log.user_id.id != request.env.user.id:
            _logger.info(
                "xn_ai_assistant: %s tried to rate log %s which is not theirs",
                request.env.user.login, log_id)
            return {'ok': False, 'error': _("Unknown answer.")}

        log.record_feedback(rating, comment)
        return {'ok': True}
