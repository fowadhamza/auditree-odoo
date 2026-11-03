# -*- coding: utf-8 -*-
from odoo import models, fields

ROLES = [
    ('hr', 'HR'),
    ('hr_head', 'HR Head'),
    ('ops', 'Operations Manager'),
    ('it', 'IT'),
    ('admin', 'Admin'),
    ('accounts', 'Accounts'),
    ('manager', 'Reporting Manager'),
]


class XnJlRole(models.Model):
    _name = 'xn.jl.role'
    _description = 'Joiner/Leaver Role'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Selection(
        [r for r in ROLES if r[0] != 'manager'], required=True)
    sequence = fields.Integer(default=10)
    user_id = fields.Many2one(
        'res.users', string='Done By', domain=[('share', '=', False)],
        help="Gets this role's steps. Left empty, the steps go to the HR role.")

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(code)', 'Each role can only be defined once.'),
    ]

    def _xn_user(self, code):
        """User holding role ``code``, or an empty recordset."""
        return self.sudo().search([('code', '=', code)], limit=1).user_id
