# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies.

from odoo import api, fields, models
import base64

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_web_push_notification = fields.Boolean(related='company_id.enable_web_push_notification',readonly=False)
    enable_bell_notification = fields.Boolean(related='company_id.enable_bell_notification',readonly=False)
    api_key = fields.Char(related='company_id.api_key',readonly=False)
    vapid = fields.Char(related='company_id.vapid',readonly=False)
    config_details = fields.Text(related='company_id.config_details',readonly=False)

