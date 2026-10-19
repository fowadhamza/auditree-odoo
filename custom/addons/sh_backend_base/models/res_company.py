# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies.

from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    enable_web_push_notification = fields.Boolean("Enable Firebase Push Notification")
    enable_bell_notification = fields.Boolean("Enable Bell Notification")
    api_key = fields.Char("Api Key")
    vapid = fields.Char("Vapid",readonly=False)
    config_details = fields.Text("Config Details")


