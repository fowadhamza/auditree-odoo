# -*- coding: utf-8 -*-
from odoo import models, fields


class ForecastRevenueOverride(models.Model):
    _name = 'forecast.revenue.override'
    _description = 'Forecast Revenue Override'
    _order = 'month desc'

    revenue_assignment_id = fields.Many2one('forecast.revenue.assignment', required=True,
                                             ondelete='cascade', string='Revenue Assignment')
    month = fields.Date(required=True, help="Any date within the target month")
    amount = fields.Float(required=True, string='Amount (INR)')
    reason = fields.Char()
