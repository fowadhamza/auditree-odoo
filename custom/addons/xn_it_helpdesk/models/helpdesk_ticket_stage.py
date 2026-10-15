# -*- coding: utf-8 -*-
from odoo import models, fields, _

XN_STATES = [
    ('new', 'New'),
    ('in_progress', 'In Progress'),
    ('on_hold', 'On Hold'),
    ('resolved', 'Resolved'),
    ('closed', 'Closed'),
]


class HelpdeskTicketStage(models.Model):
    _inherit = 'helpdesk.ticket.stage'

    xn_state = fields.Selection(
        XN_STATES, string='IT Status',
        help="What this stage means to the IT Helpdesk. Drives the buttons, "
             "the resolution-note check, the resolved/closed timestamps and "
             "the dashboard. Leave empty for stages the IT Helpdesk ignores.")
    xn_ticket_count = fields.Integer(
        string='Tickets', compute='_compute_xn_ticket_count')

    def _compute_xn_ticket_count(self):
        # Counted as the current user, so employees see their own tickets
        # and the IT team sees everything.
        data = self.env['helpdesk.ticket']._read_group(
            [('stage_id', 'in', self.ids)], ['stage_id'], ['__count'])
        counts = {stage.id: count for stage, count in data}
        for stage in self:
            stage.xn_ticket_count = counts.get(stage.id, 0)

    def action_xn_open_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'xn_it_helpdesk.action_xn_helpdesk_ticket_all')
        action.update({
            'name': _('%s Tickets', self.name),
            'domain': [('stage_id', '=', self.id)],
            'context': {},
        })
        return action
