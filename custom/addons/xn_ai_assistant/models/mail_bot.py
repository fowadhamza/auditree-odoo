# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError

import logging

from markupsafe import Markup, escape

_logger = logging.getLogger(__name__)

# The states mail_bot walks a new user through before it will hold a normal
# conversation. See mail_bot/models/res_users.py.
ONBOARDING_STATES = (
    False,
    'not_initialized',
    'onboarding_emoji',
    'onboarding_attachement',
    'onboarding_command',
    'onboarding_ping',
)


class MailBot(models.AbstractModel):
    _inherit = 'mail.bot'

    def _get_answer(self, record, body, values, command=False):
        """Answer with the assistant instead of OdooBot's product tour.

        The first version of this called super() first and only fell through
        when core had nothing to say. That never happened: mail_bot's
        onboarding sequence answers every message until the user completes it,
        so a question like "who am i" got "Not sure what you are doing, type
        /" and the assistant was never reached.

        Slash commands still go to core, so /help and friends behave normally.
        Everything else is a question for the assistant, and the tour is
        retired on first use -- this deployment's bot exists to answer HR
        questions, not to teach people the Odoo UI.
        """
        if command:
            return super()._get_answer(record, body, values, command)
        if not body:
            return super()._get_answer(record, body, values, command)
        if not (self._is_bot_in_private_channel(record)
                or self._is_bot_pinged(values)):
            return super()._get_answer(record, body, values, command)

        user = self.env.user
        if user.odoobot_state in ONBOARDING_STATES:
            user.sudo().write({'odoobot_state': 'idle', 'odoobot_failed': False})

        try:
            # No history: the Discuss bot answers each message on its own.
            # Threading a conversation through mail.message is a separate
            # exercise and the launcher is the surface being kept.
            reply = (self.env['ai.assistant'].answer(body) or {}).get('text')
        except UserError as exc:
            # ai.service raises UserError for refusals the asker should see:
            # kill switch off, budget exhausted, provider unreachable.
            return escape(str(exc))
        except Exception:  # noqa: BLE001
            _logger.exception("xn_ai_assistant: assistant failed for %s",
                              user.login)
            return escape(_("Sorry, something went wrong on my side."))

        if not reply:
            return escape(_("Sorry, I did not understand that."))
        # escape() first, then convert newlines: the model's output is
        # untrusted text and must never reach the chatter as live markup.
        return Markup('<br/>').join(escape(reply).split('\n'))
