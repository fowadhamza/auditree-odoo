# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ForecastRevenueAssignment(models.Model):
    _name = 'forecast.revenue.assignment'
    _description = 'Forecast Revenue Assignment'
    _order = 'start_month desc'

    employee_id = fields.Many2one('forecast.employee', required=True, ondelete='cascade')
    client_id = fields.Many2one('forecast.client', required=True, ondelete='restrict')
    bill_rate = fields.Float(required=True)
    currency_id = fields.Many2one('res.currency', required=True,
                                   default=lambda self: self.env.company.currency_id)
    exchange_rate = fields.Float(default=1.0, help="Multiplier to convert bill_rate to INR")
    allocation_pct = fields.Float(default=100.0)
    start_month = fields.Date(required=True)
    end_month = fields.Date(help="Leave empty for an ongoing assignment")
    monthly_amount_inr = fields.Float(
        string='Monthly Amount (INR)', compute='_compute_monthly_amount_inr', store=True,
        help="bill_rate x allocation_pct x exchange_rate")

    @api.depends('bill_rate', 'allocation_pct', 'exchange_rate')
    def _compute_monthly_amount_inr(self):
        for rec in self:
            rec.monthly_amount_inr = rec.bill_rate * (rec.allocation_pct / 100.0) * rec.exchange_rate
