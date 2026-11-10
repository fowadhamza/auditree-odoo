# -*- coding: utf-8 -*-
from odoo import models, fields

APPROVAL_STATES = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Withdrawn'),
]


class HelpdeskApproval(models.Model):
    """One approval request on an IT ticket: who was asked, by whom, why,
    and what they decided.

    This is the audit trail. Rows are only ever created and decided through
    the ticket's buttons (sudo, after checking the user); nobody has write or
    delete rights on the model, and a ticket that has approval history
    cannot be deleted (ondelete='restrict'). A ticket can collect several
    rows: a withdrawn request followed by a new one, or a second approval
    after a rejected ticket is reopened.
    """
    _name = 'xn.helpdesk.approval'
    _description = 'IT Ticket Approval'
    _order = 'request_date desc, id desc'
    _rec_name = 'ticket_id'

    ticket_id = fields.Many2one(
        'helpdesk.ticket', string='Ticket', required=True, index=True,
        ondelete='restrict', readonly=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True)
    approver_id = fields.Many2one(
        'res.users', string='Approver', required=True, index=True, readonly=True)
    requested_by_id = fields.Many2one(
        'res.users', string='Requested By', required=True, readonly=True,
        default=lambda self: self.env.user)
    request_date = fields.Datetime(
        string='Requested On', required=True, readonly=True,
        default=fields.Datetime.now)
    request_note = fields.Text(string='What Needs Approval', readonly=True)
    state = fields.Selection(
        APPROVAL_STATES, string='Status', required=True, index=True,
        default='pending', readonly=True)
    decided_by_id = fields.Many2one('res.users', string='Decided By', readonly=True)
    decision_date = fields.Datetime(string='Decided On', readonly=True)
    decision_comment = fields.Text(string='Approver Comments', readonly=True)
