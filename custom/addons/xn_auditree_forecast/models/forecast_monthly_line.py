# -*- coding: utf-8 -*-
from odoo import models, fields


class ForecastMonthlyLine(models.Model):
    _name = 'forecast.monthly.line'
    _description = 'Forecast Monthly Line (generated)'
    _order = 'month, line_type'

    month = fields.Date(required=True)
    line_type = fields.Selection([
        ('revenue', 'Revenue'),
        ('salary', 'Salary'),
        ('expense', 'Expense'),
        ('cash_other', 'Other Cash Movement'),
        ('adjustment', 'Financial Adjustment'),
    ], required=True)
    direction = fields.Selection([
        ('inflow', 'Inflow'),
        ('outflow', 'Outflow'),
    ], required=True)
    employee_id = fields.Many2one('forecast.employee')
    client_id = fields.Many2one('forecast.client')
    category = fields.Char()
    amount = fields.Float(required=True, string='Amount (INR)')
    description = fields.Char()
