# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class HelpdeskApprovalWizard(models.TransientModel):
    """The one dialog behind Request Approval, Approve and Reject.

    All checks (IT only, pending approver only, comment required on reject)
    live on helpdesk.ticket, so they hold however the methods are reached.
    """
    _name = 'xn.helpdesk.approval.wizard'
    _description = 'IT Ticket Approval Step'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', required=True)
    mode = fields.Selection(
        [('request', 'Request Approval'),
         ('approve', 'Approve'),
         ('reject', 'Reject')],
        required=True)
    approver_id = fields.Many2one(
        'res.users', string='Approver', domain=[('share', '=', False)])
    note = fields.Text(string='Details')

    def action_confirm(self):
        self.ensure_one()
        if self.mode == 'request':
            if not self.approver_id:
                raise UserError(_("Pick who should approve this request."))
            self.ticket_id._xn_request_approval(self.approver_id, self.note)
        else:
            self.ticket_id._xn_decide_approval(self.mode == 'approve', self.note)
        return {'type': 'ir.actions.act_window_close'}
