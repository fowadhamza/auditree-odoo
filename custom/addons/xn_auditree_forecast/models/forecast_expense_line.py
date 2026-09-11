# -*- coding: utf-8 -*-
from odoo import models, fields


class ForecastExpenseLine(models.Model):
    _name = 'forecast.expense.line'
    _description = 'Forecast Expense Line Item'
    _order = 'start_month desc'

    name = fields.Char(required=True)
    category = fields.Char()
    annual_total = fields.Float(required=True, help="Total amount for the item's full recurrence range")
    recurrence = fields.Selection([
        ('monthly', 'Spread Monthly'),
        ('quarterly', 'Quarterly'),
        ('one_time', 'One-time'),
    ], required=True, default='monthly')
    start_month = fields.Date(required=True)
    end_month = fields.Date(help="Leave empty to run to the end of the forecast window")
