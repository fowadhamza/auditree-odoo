# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import json
import logging
import os
import re
import time

import requests

_logger = logging.getLogger(__name__)

# Aadhaar: 12 digits, commonly written in groups of four. The leading digit is
# never 0 or 1 in a real number, which keeps this off most invoice totals and
# phone numbers.
AADHAAR_RE = re.compile(r'\b[2-9]{1}[0-9]{3}[ -]?[0-9]{4}[ -]?[0-9]{4}\b')
# PAN: five letters, four digits, one letter.
PAN_RE = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b')

DEFAULT_API_VERSION = '2024-10-21'
API_KEY_ENV_VAR = 'AUDITREE_AI_API_KEY'


class AiService(models.AbstractModel):
    """The only place in this database that talks to an AI provider.

    Callers use `call()`. Everything else here is the guard rail it runs
    behind: kill switch, monthly budget, size limit, redaction, logging.
    """

    _name = 'ai.service'
    _description = 'AI Service'

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @api.model
    def _param(self, key, default=None):
        """Read an xn_ai.* config parameter, falling back to `default`.

        get_param returns False for a key that was never set, and False is not
        equal to None or '' -- so a naive `not in (None, '')` check hands the
        caller False and `int(False)` is 0. That silently turned every unset
        default into zero, which made the input size limit reject a 64
        character prompt. Parameters are always strings when set, so a plain
        falsy test is both correct and safe: "0" is a non-empty string and
        survives it.
        """
        value = self.env['ir.config_parameter'].sudo().get_param('xn_ai.' + key)
        return value if value else default

    @api.model
    def _api_key(self):
        """Read the key from the environment first, config parameter second.

        An environment variable is not readable through the Odoo UI and does
        not travel in a database dump, which a config parameter does. The
        fallback exists so local development is not blocked, and it logs a
        warning so it does not quietly become the production arrangement.
        """
        key = os.environ.get(API_KEY_ENV_VAR)
        if key:
            return key
        key = self._param('azure_api_key')
        if key:
            _logger.warning(
                "xn_ai_core: using the API key from ir.config_parameter. Set "
                "the %s environment variable instead -- config parameters are "
                "readable in the UI and travel in database dumps.",
                API_KEY_ENV_VAR)
        return key

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    @api.model
    def _redact(self, text):
        """Mask Aadhaar and PAN patterns. Returns (text, count).

        This is a backstop, not the control. Tools are expected to read named
        fields rather than whole records, so in a correct system this never
        fires. A non-zero redaction_count on a log row is therefore a bug
        report about the caller, and is surfaced as such in the tree view.
        """
        count = 0
        text, n = AADHAAR_RE.subn('[AADHAAR REDACTED]', text)
        count += n
        text, n = PAN_RE.subn('[PAN REDACTED]', text)
        count += n
        return text, count

    @api.model
    def _budget_remaining(self):
        """Tokens left this calendar month, or None when no budget is set."""
        budget = self._param('monthly_token_budget')
        if not budget:
            return None
        try:
            budget = int(budget)
        except (TypeError, ValueError):
            _logger.warning("xn_ai_core: monthly_token_budget is not a number: %r",
                            budget)
            return None
        if budget <= 0:
            return None
        month_start = fields.Date.context_today(self).replace(day=1)
        used = self.env['ai.request.log'].sudo().tokens_used_since(month_start)
        return budget - used

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @api.model
    def call(self, messages, purpose, tools=None, max_tokens=None,
             res_model=None, res_id=None):
        """Send `messages` to the configured provider and return the reply.

        :param messages: list of {"role": ..., "content": ...} dicts
        :param purpose: short slug naming the calling feature, for the log
        :param tools: optional list of tool definitions
        :param max_tokens: output ceiling; falls back to the configured default
        :return: dict with keys `content`, `tool_calls`, `log_id`

        Raises UserError when the call is refused or the provider fails. The
        message is safe to show a user; provider detail goes to the log.
        """
        started = time.time()
        log_values = {
            'purpose': purpose,
            'provider': self._param('provider', 'azure'),
            'deployment': self._param('azure_deployment'),
            'res_model': res_model,
            'res_id': res_id,
        }

        if self._param('enabled', 'False') != 'True':
            return self._blocked(log_values,
                                 _("AI features are currently switched off."))

        remaining = self._budget_remaining()
        if remaining is not None and remaining <= 0:
            return self._blocked(
                log_values,
                _("The monthly AI budget for this database has been used up."))

        payload_text = json.dumps(messages)
        payload_text, redactions = self._redact(payload_text)
        log_values['redaction_count'] = redactions
        if redactions:
            _logger.warning(
                "xn_ai_core: redacted %d identifier(s) from a %s payload. The "
                "caller passed data it should have filtered.",
                redactions, purpose)
        messages = json.loads(payload_text)

        max_input = int(self._param('max_input_chars', 200000))
        if len(payload_text) > max_input:
            return self._blocked(
                log_values,
                _("That request is too large to send (%(size)s characters, "
                  "limit %(limit)s).",
                  size=len(payload_text), limit=max_input))

        if not max_tokens:
            max_tokens = int(self._param('max_tokens_default', 2048))

        try:
            result = self._dispatch(messages, tools, max_tokens)
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised as UserError
            log_values.update({
                'state': 'error',
                'error_message': str(exc)[:2000],
                'latency_ms': int((time.time() - started) * 1000),
            })
            self._write_log(log_values, messages, None)
            _logger.exception("xn_ai_core: %s call failed", purpose)
            raise UserError(
                _("The AI service could not be reached. Please try again "
                  "shortly; if it keeps happening, tell your administrator."))

        log_values.update({
            'state': 'success',
            'input_tokens': result.get('input_tokens', 0),
            'output_tokens': result.get('output_tokens', 0),
            'latency_ms': int((time.time() - started) * 1000),
        })
        log = self._write_log(log_values, messages, result.get('raw'))
        result['log_id'] = log.id
        return result

    @api.model
    def _blocked(self, log_values, message):
        log_values.update({'state': 'blocked', 'error_message': message})
        self._write_log(log_values, None, None)
        raise UserError(message)

    @api.model
    def _write_log(self, values, request_payload, response_payload):
        if self._param('log_payloads', 'False') == 'True':
            if request_payload is not None:
                values['request_payload'] = json.dumps(request_payload)[:64000]
            if response_payload is not None:
                values['response_payload'] = json.dumps(response_payload)[:64000]
        return self.env['ai.request.log'].sudo().create(values)

    # ------------------------------------------------------------------
    # Provider adapters
    # ------------------------------------------------------------------

    @api.model
    def _dispatch(self, messages, tools, max_tokens):
        provider = self._param('provider', 'azure')
        if provider == 'azure':
            return self._call_azure(messages, tools, max_tokens)
        raise UserError(_("Unknown AI provider configured: %s", provider))

    @api.model
    def _call_azure(self, messages, tools, max_tokens):
        endpoint = (self._param('azure_endpoint') or '').rstrip('/')
        deployment = self._param('azure_deployment')
        api_version = self._param('azure_api_version', DEFAULT_API_VERSION)
        api_key = self._api_key()

        missing = [name for name, value in (
            ('endpoint', endpoint), ('deployment', deployment), ('API key', api_key))
            if not value]
        if missing:
            raise UserError(
                _("The AI service is not configured yet (missing: %s).",
                  ', '.join(missing)))

        url = "%s/openai/deployments/%s/chat/completions?api-version=%s" % (
            endpoint, deployment, api_version)
        body = {'messages': messages, 'max_tokens': max_tokens}
        if tools:
            body['tools'] = tools
            body['tool_choice'] = 'auto'

        response = requests.post(
            url,
            headers={'api-key': api_key, 'Content-Type': 'application/json'},
            json=body,
            timeout=int(self._param('timeout_seconds', 60)),
        )
        response.raise_for_status()
        data = response.json()

        choice = (data.get('choices') or [{}])[0]
        message = choice.get('message') or {}
        usage = data.get('usage') or {}
        return {
            'content': message.get('content') or '',
            'tool_calls': message.get('tool_calls') or [],
            'finish_reason': choice.get('finish_reason'),
            'input_tokens': usage.get('prompt_tokens', 0),
            'output_tokens': usage.get('completion_tokens', 0),
            'raw': data,
        }
