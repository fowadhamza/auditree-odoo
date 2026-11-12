# -*- coding: utf-8 -*-
from odoo import models, fields, api


class XnActivityNote(models.Model):
    """A note on a person's day: client visit, offline field work, etc.

    Employees note their own days; HR can note anyone's. Only the author can
    change or delete a note (record rules).
    """
    _name = 'xn.activity.note'
    _description = 'Activity Day Note'
    _order = 'date desc, id desc'

    def _default_employee(self):
        return self.env.user.employee_id

    employee_id = fields.Many2one('hr.employee', required=True,
                                  ondelete='cascade', index=True,
                                  default=_default_employee)
    date = fields.Date(required=True, index=True,
                       default=fields.Date.context_today)
    note = fields.Char(required=True)
    author_id = fields.Many2one('res.users', string='Author',
                                related='create_uid', store=True)

    def _xn_pairs(self):
        return {('emp:%d' % n.employee_id.id, n.date) for n in self}

    @api.model_create_multi
    def create(self, vals_list):
        notes = super().create(vals_list)
        self.env['xn.activity.day']._xn_recompute(notes._xn_pairs())
        return notes

    def write(self, vals):
        before = self._xn_pairs()
        res = super().write(vals)
        self.env['xn.activity.day']._xn_recompute(before | self._xn_pairs())
        return res

    def unlink(self):
        before = self._xn_pairs()
        res = super().unlink()
        self.env['xn.activity.day']._xn_recompute(before)
        return res
