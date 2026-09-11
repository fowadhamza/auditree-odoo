# -*- coding: utf-8 -*-
from odoo import models, fields


class ForecastClient(models.Model):
    _name = 'forecast.client'
    _description = 'Forecast Client'
    _order = 'name'

    name = fields.Char(required=True)
    category = fields.Char(help="e.g. Auditeo, Continusys, IFS, Common pool")
    account_owner = fields.Char()
    active = fields.Boolean(default=True)
