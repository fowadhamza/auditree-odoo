# -*- coding: utf-8 -*-
from odoo import models, fields


class HelpdeskTicketTeam(models.Model):
    _inherit = 'helpdesk.ticket.team'

    xn_default_approver_id = fields.Many2one(
        'res.users', string='Default Approver',
        domain=[('share', '=', False)],
        help="Suggested when IT asks for management approval on one of this "
             "team's tickets. IT can pick someone else on each request.")
