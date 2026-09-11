# -*- coding: utf-8 -*-
from odoo import models, fields


class ForecastCashMovement(models.Model):
    _name = 'forecast.cash.movement'
    _description = 'Forecast Other Cash Movement'
    _order = 'date desc'

    date = fields.Date(required=True)
    movement_type = fields.Selection([
        ('inflow', 'Inflow'),
        ('outflow', 'Outflow'),
    ], required=True)
    amount = fields.Float(required=True)
    category = fields.Char(help="e.g. Opening Balance, Partner Loan Repayment")
    description = fields.Char()
