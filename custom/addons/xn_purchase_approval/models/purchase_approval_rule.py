# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class XnPurchaseApprovalRule(models.Model):
    _name = 'xn.purchase.approval.rule'
    _description = 'Purchase Approval Rule'
    _order = 'min_amount desc, sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
        help="Leave empty to apply to every company.")
    currency_id = fields.Many2one(
        'res.currency', compute='_compute_currency_id')
    min_amount = fields.Monetary(
        string='Minimum Amount', currency_field='currency_id',
        help="Orders whose total (in company currency) is at least this "
             "amount use this rule. When several rules match, the one with "
             "the highest minimum wins.")
    approver_id = fields.Many2one(
        'res.users', string='Approver', required=True,
        domain=[('share', '=', False)])

    @api.depends('company_id')
    def _compute_currency_id(self):
        for rule in self:
            rule.currency_id = (rule.company_id or self.env.company).currency_id

    @api.model
    def _xn_find_for_order(self, order):
        """Return the rule that governs ``order``, or an empty recordset."""
        amount = order.currency_id._convert(
            order.amount_total, order.company_id.currency_id,
            order.company_id, order.date_order or fields.Date.today())
        rules = self.search([
            ('company_id', 'in', [False, order.company_id.id]),
        ])
        # _order puts the highest minimum first.
        return rules.filtered(lambda r: amount >= r.min_amount)[:1]
