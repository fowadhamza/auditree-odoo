# -*- coding: utf-8 -*-
from odoo import models, fields


class XnJlStep(models.Model):
    _inherit = 'xn.jl.step'

    xn_raise_ticket = fields.Boolean(
        string='Raises an IT Ticket',
        help="When the checklist starts, raise an IT Helpdesk ticket in HR's "
             "name for this step and mark the step done.")
