# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    signatory_approved = fields.Boolean(string='Signatory Approved', default=False, copy=False)
    signatory_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)
    signatory_approved_date = fields.Datetime(string='Approved On', readonly=True, copy=False)

    invoice_currency_rate = fields.Float(string='Conversion Rate', digits=(12, 6), copy=False)

    def action_signatory_approve(self):
        for move in self:
            move.write({
                'signatory_approved': True,
                'signatory_id': self.env.user.id,
                'signatory_approved_date': fields.Datetime.now(),
            })

    def action_signatory_reset(self):
        for move in self:
            move.write({
                'signatory_approved': False,
                'signatory_id': False,
                'signatory_approved_date': False,
            })
