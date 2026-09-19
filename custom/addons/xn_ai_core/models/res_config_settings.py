# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    xn_ai_enabled = fields.Boolean(
        string='Enable AI features',
        config_parameter='xn_ai.enabled',
        help="The kill switch. Turning this off stops every AI call "
             "immediately, with no restart and no deployment.")

    xn_ai_provider = fields.Selection(
        [('azure', 'Microsoft Azure')],
        string='Provider', default='azure',
        config_parameter='xn_ai.provider')

    xn_ai_azure_endpoint = fields.Char(
        string='Endpoint',
        config_parameter='xn_ai.azure_endpoint',
        help="For example https://auditree-chat.cognitiveservices.azure.com/")

    xn_ai_azure_deployment = fields.Char(
        string='Deployment name',
        config_parameter='xn_ai.azure_deployment',
        help="The deployment, not the model. Pointing an existing deployment "
             "at a newer model is how you change models without touching Odoo.")

    xn_ai_azure_api_version = fields.Char(
        string='API version',
        config_parameter='xn_ai.azure_api_version',
        default='2024-10-21')

    xn_ai_monthly_token_budget = fields.Integer(
        string='Monthly token budget',
        config_parameter='xn_ai.monthly_token_budget',
        help="Calls are refused once this month's successful calls have used "
             "this many tokens. Zero means no budget is enforced.")

    xn_ai_max_tokens_default = fields.Integer(
        string='Default output limit',
        config_parameter='xn_ai.max_tokens_default',
        default=2048,
        help="Maximum tokens a single reply may generate when the caller does "
             "not specify one.")

    xn_ai_log_payloads = fields.Boolean(
        string='Store prompts and responses',
        config_parameter='xn_ai.log_payloads',
        help="Off by default and should usually stay off. Turning it on makes "
             "the request log a second copy of whatever employee data was "
             "sent, under different access rules than the records it came "
             "from. Use it to debug, then turn it back off.")

    xn_ai_api_key_present = fields.Boolean(
        string='API key configured',
        compute='_compute_xn_ai_api_key_present',
        help="Whether a key is readable from the environment or a config "
             "parameter. The key itself is never shown here.")

    @api.depends('xn_ai_provider')
    def _compute_xn_ai_api_key_present(self):
        has_key = bool(self.env['ai.service']._api_key())
        for record in self:
            record.xn_ai_api_key_present = has_key
