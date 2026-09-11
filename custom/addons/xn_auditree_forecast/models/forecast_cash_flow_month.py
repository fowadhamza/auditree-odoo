# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ForecastCashFlowMonth(models.Model):
    _name = 'forecast.cash.flow.month'
    _description = 'Forecast Cash Flow Summary (generated)'
    _order = 'month'

    month = fields.Date(required=True)
    opening_balance = fields.Float(string='Opening Balance (INR)')
    total_inflow = fields.Float(string='Total Inflow (INR)')
    total_outflow = fields.Float(string='Total Outflow (INR)')
    net_change = fields.Float(string='Net Change (INR)', compute='_compute_net_change', store=True)
    closing_balance = fields.Float(string='Closing Balance (INR)')

    @api.depends('total_inflow', 'total_outflow')
    def _compute_net_change(self):
        for rec in self:
            rec.net_change = rec.total_inflow - rec.total_outflow
