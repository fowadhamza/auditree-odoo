# -*- coding: utf-8 -*-
from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    xn_is_recruitment_agency = fields.Boolean(string='Recruitment Agency')
    xn_agency_fee_type = fields.Selection(
        [('one_month', "One month's salary of the hire"),
         ('percent', '8.33% of annual CTC')],
        string='Agency Fee',
        help="Used to work out the fee on a joined candidate from the offered CTC.")
