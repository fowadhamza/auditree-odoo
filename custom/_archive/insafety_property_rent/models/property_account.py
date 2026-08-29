# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class PropertyAccount(models.Model):
    _inherit = 'account.account'
    building_id = fields.Many2one('insafety.property.building', string="Building to Distribute Costs")

