# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)


class AiAssistantController(http.Controller):
    """JSON endpoint for the systray assistant.

    auth='user' is the whole security story: the route runs in the session of
    whoever is logged in, so request.env is their environment and every tool
    the assistant calls is filtered by their own record rules. There is no
    user id in the payload and nothing here to spoof.

    A plain controller rather than an ORM call_kw on ai.assistant: an
    AbstractModel has no ir.model.access rows, so exposing it to the web
    client means reasoning about method-level access checks. One route with
    one argument is easier to hold in your head and easier to audit.
    """

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
            answer = request.env['ai.assistant'].answer(question)
        except UserError as exc:
            # Refusals the asker should see: switched off, budget spent,
            # provider unreachable.
            return {'ok': False, 'error': str(exc)}
        except Exception:  # noqa: BLE001
            _logger.exception(
                "xn_ai_assistant: systray request failed for %s",
                request.env.user.login)
            return {'ok': False,
                    'error': _("Sorry, something went wrong on my side.")}

        return {'ok': True,
                'answer': answer or _("Sorry, I did not understand that.")}
