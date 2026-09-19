# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class AiRequestLog(models.Model):
    """One row per outbound AI call, successful or not.

    This is the record of what the business spent and what was asked, and it
    is what the monthly budget in ai.service is computed from. It is not a
    debugging aid -- prompt and response bodies are only stored when
    xn_ai.log_payloads is explicitly turned on, because storing them makes
    this table a second copy of personal data governed by different access
    rules than the models it came from.
    """

    _name = 'ai.request.log'
    _description = 'AI Request Log'
    _order = 'create_date desc, id desc'
    _rec_name = 'purpose'

    purpose = fields.Char(
        string='Purpose', required=True, readonly=True, index=True,
        help="Which feature made the call, e.g. hr_assistant or forecast_commentary.")
    user_id = fields.Many2one(
        'res.users', string='User', readonly=True, index=True,
        default=lambda self: self.env.user)
    company_id = fields.Many2one(
        'res.company', string='Company', readonly=True,
        default=lambda self: self.env.company)

    provider = fields.Char(string='Provider', readonly=True)
    deployment = fields.Char(
        string='Deployment', readonly=True,
        help="The provider-side deployment name, not the underlying model. "
             "Deployments are stable; the model behind one may change.")

    input_tokens = fields.Integer(string='Input Tokens', readonly=True)
    output_tokens = fields.Integer(string='Output Tokens', readonly=True)
    total_tokens = fields.Integer(
        string='Total Tokens', compute='_compute_total_tokens', store=True)
    latency_ms = fields.Integer(string='Latency (ms)', readonly=True)

    state = fields.Selection(
        [('success', 'Success'),
         ('error', 'Error'),
         ('blocked', 'Blocked')],
        string='Result', required=True, readonly=True, index=True,
        help="Blocked means this module refused to make the call -- kill "
             "switch off, budget exhausted, or input too large. No provider "
             "request was sent and nothing was billed.")
    error_message = fields.Text(string='Detail', readonly=True)

    redaction_count = fields.Integer(
        string='Redactions', readonly=True,
        help="How many Aadhaar or PAN patterns were masked before sending. "
             "Anything above zero means a caller passed data it should have "
             "filtered out, and that caller needs fixing -- the backstop "
             "firing is not a success.")

    res_model = fields.Char(string='Related Model', readonly=True)
    res_id = fields.Integer(string='Related Record', readonly=True)

    request_payload = fields.Text(
        string='Request', readonly=True,
        help="Only populated when payload logging is enabled in Settings.")
    response_payload = fields.Text(
        string='Response', readonly=True,
        help="Only populated when payload logging is enabled in Settings.")

    @api.depends('input_tokens', 'output_tokens')
    def _compute_total_tokens(self):
        for log in self:
            log.total_tokens = (log.input_tokens or 0) + (log.output_tokens or 0)

    @api.model
    def tokens_used_since(self, start):
        """Total tokens billed by successful calls since `start`.

        Blocked and errored calls are excluded: a blocked call never reached
        the provider, and an errored one is not reliably billed. Counting
        either would make the budget tighten itself on failure, which is the
        wrong direction when something is already going wrong.
        """
        self.env.cr.execute("""
            SELECT COALESCE(SUM(COALESCE(input_tokens, 0)
                              + COALESCE(output_tokens, 0)), 0)
              FROM ai_request_log
             WHERE state = 'success'
               AND create_date >= %s
        """, (start,))
        return self.env.cr.fetchone()[0] or 0
