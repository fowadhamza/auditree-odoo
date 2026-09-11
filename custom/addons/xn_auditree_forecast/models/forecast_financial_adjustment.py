# -*- coding: utf-8 -*-
from odoo import models, fields


class ForecastFinancialAdjustment(models.Model):
    _name = 'forecast.financial.adjustment'
    _description = 'Forecast Financial Adjustment'
    _order = 'month desc'

    month = fields.Date(required=True, help="Any date within the target month")
    adjustment_type = fields.Selection([
        ('income_tax', 'Income Tax'),
        ('zakat', 'Zakat'),
        ('partner_drawing', 'Partner Drawing'),
        ('reserve_transfer', 'Reserve Transfer'),
    ], required=True)
    amount = fields.Float(required=True)
    notes = fields.Text()
