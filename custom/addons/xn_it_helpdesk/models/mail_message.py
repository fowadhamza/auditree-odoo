# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import AccessError
from odoo.osv import expression


class MailMessage(models.Model):
    """Keep internal IT notes on tickets away from employees.

    Odoo hides internal notes ("Log note") from portal users only; any
    internal user who can read a record also reads its notes. Employees can
    read their own tickets, so without this they would see what the IT team
    writes to each other. Applies to helpdesk.ticket messages only.

    Scoped to members of "Raise IT Tickets": users outside that group cannot
    raise tickets, so their message searches are left exactly as core does
    them. That is what lets the module be trialled on production without
    touching anyone else's chatter. (A non-member that IT adds as a follower
    of a ticket would see its notes -- don't, during the trial.)
    """
    _inherit = 'mail.message'

    @api.model
    def _xn_hide_it_notes(self):
        """True for a ticket requester outside the IT team. Share users are
        already restricted by core mail, and the superuser sees everything."""
        user = self.env.user
        return (not self.env.is_superuser()
                and user._is_internal()
                and user.has_group('xn_it_helpdesk.group_xn_helpdesk_requester')
                and not user.has_group('helpdesk_mgmt.group_helpdesk_user_own'))

    @api.model
    def _xn_it_note_domain(self):
        """Messages a non-IT employee may see: anything not on a ticket, the
        ticket's tracked history, replies, and notes they wrote themselves."""
        return [
            '|', '|', '|',
            ('model', '!=', 'helpdesk.ticket'),
            ('message_type', '!=', 'comment'),
            ('author_id', '=', self.env.user.partner_id.id),
            '&', ('is_internal', '=', False), ('subtype_id.internal', '=', False),
        ]

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        if self._xn_hide_it_notes():
            domain = expression.AND([self._xn_it_note_domain(), domain])
        return super()._search(domain, offset, limit, order, access_rights_uid)

    def check_access_rule(self, operation):
        super().check_access_rule(operation)
        if operation != 'read' or not self or not self._xn_hide_it_notes():
            return
        on_tickets = self.sudo().filtered(lambda m: m.model == 'helpdesk.ticket')
        if not on_tickets:
            return
        visible = self.sudo().search(
            [('id', 'in', on_tickets.ids)] + self._xn_it_note_domain())
        if len(visible) != len(on_tickets):
            raise AccessError(_("Internal IT notes are visible only to the IT team."))
