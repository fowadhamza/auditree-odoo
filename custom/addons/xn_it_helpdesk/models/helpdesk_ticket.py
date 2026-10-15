# -*- coding: utf-8 -*-
from datetime import timedelta

from markupsafe import Markup

from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import is_html_empty
import logging

_logger = logging.getLogger(__name__)

# Stages a ticket counts as finished in. Reaching either needs resolution notes.
XN_DONE_STATES = ('resolved', 'closed')


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    name = fields.Char(string='Subject')
    priority = fields.Selection(
        selection=[
            ('0', 'Low'),
            ('1', 'Medium'),
            ('2', 'High'),
            ('3', 'Critical'),
        ],
        tracking=True,
    )
    category_id = fields.Many2one(tracking=True)
    team_id = fields.Many2one(tracking=True)

    # --- Requester -------------------------------------------------------
    # Snapshots, filled from the employee record when the ticket is raised so
    # a later transfer does not rewrite the history of old tickets.
    xn_employee_id = fields.Many2one(
        'hr.employee', string='Employee', index=True, tracking=True,
        compute='_compute_xn_employee_id', store=True, readonly=False)
    xn_employee_code = fields.Char(
        string='Employee ID', compute='_compute_xn_employee_details',
        store=True, readonly=False,
        help="The employee's Badge ID at the time the ticket was raised.")
    xn_department_id = fields.Many2one(
        'hr.department', string='Department', index=True,
        compute='_compute_xn_employee_details', store=True, readonly=False)

    # --- Status and resolution ------------------------------------------
    xn_stage_state = fields.Selection(
        related='stage_id.xn_state', string='IT Status', store=True)
    xn_resolution_note = fields.Html(
        string='Resolution Details', copy=False,
        help="What was wrong and what was done. Required before the ticket "
             "can be marked Resolved or Closed; the employee sees it.")
    xn_resolved_date = fields.Datetime(string='Resolved On', readonly=True, copy=False)
    xn_closed_date = fields.Datetime(string='Closed On', readonly=True, copy=False)
    xn_reopen_count = fields.Integer(string='Times Reopened', readonly=True, copy=False)
    xn_resolution_hours = fields.Float(
        string='Resolution Time (Hours)', group_operator='avg',
        compute='_compute_xn_resolution_hours', store=True,
        help="Hours from submission to the latest resolution.")

    # Files picked on the new-ticket form. They are uploaded before the ticket
    # exists; create() moves them onto the ticket so they show in the chatter.
    xn_attachment_ids = fields.Many2many(
        'ir.attachment', 'xn_helpdesk_ticket_upload_rel', 'ticket_id', 'attachment_id',
        string='Attachments', copy=False)

    # --- Who is looking ----------------------------------------------------
    xn_is_it_user = fields.Boolean(compute='_compute_xn_is_it_user')
    xn_is_requester = fields.Boolean(compute='_compute_xn_is_requester')

    # ---------------------------------------------------------------------
    # Computes
    # ---------------------------------------------------------------------

    @api.depends('partner_id')
    def _compute_xn_employee_id(self):
        Users = self.env['res.users'].sudo()
        Employees = self.env['hr.employee'].sudo()
        for ticket in self:
            employee = Employees
            if ticket.partner_id:
                user = Users.search([('partner_id', '=', ticket.partner_id.id)], limit=1)
                employee = user.employee_id or Employees.search(
                    [('work_contact_id', '=', ticket.partner_id.id)], limit=1)
            ticket.xn_employee_id = employee or ticket.xn_employee_id

    @api.depends('xn_employee_id')
    def _compute_xn_employee_details(self):
        for ticket in self:
            # sudo: Badge ID is restricted to HR officers.
            employee = ticket.xn_employee_id.sudo()
            if employee:
                ticket.xn_employee_code = employee.barcode or False
                ticket.xn_department_id = employee.department_id
            else:
                ticket.xn_employee_code = ticket.xn_employee_code
                ticket.xn_department_id = ticket.xn_department_id

    @api.depends('create_date', 'xn_resolved_date')
    def _compute_xn_resolution_hours(self):
        for ticket in self:
            if ticket.create_date and ticket.xn_resolved_date:
                delta = ticket.xn_resolved_date - ticket.create_date
                ticket.xn_resolution_hours = delta.total_seconds() / 3600.0
            else:
                ticket.xn_resolution_hours = 0.0

    @api.depends_context('uid')
    def _compute_xn_is_it_user(self):
        is_it = self.env.user.has_group('helpdesk_mgmt.group_helpdesk_user_own')
        for ticket in self:
            ticket.xn_is_it_user = is_it

    @api.depends('partner_id')
    @api.depends_context('uid')
    def _compute_xn_is_requester(self):
        partner = self.env.user.partner_id
        for ticket in self:
            ticket.xn_is_requester = ticket.partner_id == partner

    @api.onchange('xn_employee_id')
    def _onchange_xn_employee_id(self):
        employee = self.xn_employee_id.sudo()
        if not employee:
            return
        partner = employee.user_id.partner_id or employee.work_contact_id
        if partner:
            self.partner_id = partner
        self.partner_name = employee.name
        self.partner_email = employee.work_email or partner.email

    @api.constrains('stage_id', 'xn_resolution_note')
    def _check_xn_resolution_note(self):
        for ticket in self:
            if (ticket.stage_id.xn_state in XN_DONE_STATES
                    and is_html_empty(ticket.xn_resolution_note)):
                raise ValidationError(_(
                    "%(ticket)s cannot be moved to %(stage)s without resolution "
                    "notes. Fill in the Resolution tab first.",
                    ticket=ticket.number, stage=ticket.stage_id.name))

    # ---------------------------------------------------------------------
    # CRUD
    # ---------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        user = self.env.user
        if 'partner_id' in fields_list and not defaults.get('partner_id'):
            defaults['partner_id'] = user.partner_id.id
            if 'partner_name' in fields_list:
                defaults.setdefault('partner_name', user.name)
            if 'partner_email' in fields_list:
                defaults.setdefault(
                    'partner_email', user.employee_id.work_email or user.email)
        if 'team_id' in fields_list and not defaults.get('team_id'):
            team = self.env.ref('xn_it_helpdesk.team_it_support', raise_if_not_found=False)
            if team and team.active:
                defaults['team_id'] = team.id
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and self._xn_is_shared_account():
            raise UserError(_(
                "Shared and system accounts cannot raise IT tickets. "
                "Please raise it from your personal login."))
        tickets = super().create(vals_list)
        for ticket in tickets.sudo():
            ticket._xn_link_uploads()
            # The requester follows the ticket so IT replies reach them.
            if ticket.partner_id:
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
            ticket._xn_send_template('xn_it_helpdesk.mail_template_ticket_received')
            ticket._xn_notify_it_team()
        return tickets

    def write(self, vals):
        if not vals.get('stage_id'):
            return super().write(vals)
        new_state = self.env['helpdesk.ticket.stage'].browse(vals['stage_id']).xn_state
        now = fields.Datetime.now()
        for ticket in self:
            ticket_vals = dict(vals)
            if ticket.stage_id.id != vals['stage_id']:
                old_state = ticket.stage_id.xn_state
                if new_state == 'resolved':
                    ticket_vals.update(xn_resolved_date=now, xn_closed_date=False)
                elif new_state == 'closed':
                    ticket_vals['xn_closed_date'] = now
                    if not ticket.xn_resolved_date:
                        ticket_vals['xn_resolved_date'] = now
                elif old_state in XN_DONE_STATES:
                    # Back to an open stage: a reopen, however it happened.
                    ticket_vals.update(
                        xn_resolved_date=False, xn_closed_date=False,
                        xn_reopen_count=ticket.xn_reopen_count + 1)
            super(HelpdeskTicket, ticket).write(ticket_vals)
        return True

    # ---------------------------------------------------------------------
    # Internal notes stay with the IT team
    # ---------------------------------------------------------------------

    def _get_mail_thread_data_attachments(self):
        """Drop files attached to internal IT notes from the chatter's
        attachment box for non-IT users. The notes themselves are filtered in
        mail.message; without this their files would still be listed here."""
        attachments = super()._get_mail_thread_data_attachments()
        Message = self.env['mail.message']
        if Message._xn_hide_it_notes():
            hidden = Message.sudo().search(
                [('model', '=', self._name), ('res_id', '=', self.id), '!']
                + Message._xn_it_note_domain())
            attachments -= hidden.attachment_ids
        return attachments

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    @api.model
    def _xn_is_shared_account(self, user=None):
        """True for a shared mailbox login (employee type 'system', added by
        xn_auditree_erp) that is not in the IT team. it@ is shared but works
        the tickets, so IT membership wins."""
        user = user or self.env.user
        if user.has_group('helpdesk_mgmt.group_helpdesk_user_own'):
            return False
        # Without xn_auditree_erp no employee has type 'system': always False.
        return any(emp.employee_type == 'system' for emp in user.sudo().employee_ids)

    def _xn_link_uploads(self):
        """Move files uploaded on the new-ticket form onto the ticket.

        The upload widget creates them with res_id 0, before the ticket
        exists. Only files the current user uploaded and that are still
        unattached are taken, so a hand-crafted id list cannot pull in
        someone else's attachment.
        """
        user = self.env.user
        for ticket in self:
            uploads = ticket.xn_attachment_ids.filtered(
                lambda a: a.res_model == ticket._name and not a.res_id
                and a.create_uid == user)
            uploads.write({'res_id': ticket.id})
            ticket.xn_attachment_ids = uploads

    @api.model
    def _xn_cron_autoclose_resolved(self):
        """Close tickets left in Resolved with no confirmation or reopen.

        The delay is the system parameter xn_it_helpdesk.autoclose_days
        (default 3); 0 turns auto-closing off.
        """
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'xn_it_helpdesk.autoclose_days', 3))
        if days <= 0:
            return
        cutoff = fields.Datetime.now() - timedelta(days=days)
        tickets = self.search([
            ('xn_stage_state', '=', 'resolved'),
            ('xn_resolved_date', '<=', cutoff),
        ])
        for ticket in tickets:
            ticket._xn_move_to('closed')
            # A notification, not a note, so the employee sees it too.
            ticket.message_post(
                body=_("Closed automatically: resolved %s days ago with no "
                       "confirmation or reopen.", days),
                message_type='notification', subtype_xmlid='mail.mt_note')
        if tickets:
            _logger.info("IT Helpdesk auto-closed %s ticket(s): %s",
                         len(tickets), ', '.join(tickets.mapped('number')))

    def _xn_get_stage(self, state):
        self.ensure_one()
        stage = self.team_id._get_applicable_stages().filtered(
            lambda s: s.xn_state == state)[:1]
        if not stage:
            label = dict(self.env['helpdesk.ticket.stage']._fields['xn_state']
                         ._description_selection(self.env))[state]
            raise UserError(_(
                "No stage is set up as \"%s\". Ask the IT administrator to set "
                "one under IT Helpdesk > Configuration > Stages.", label))
        return stage

    def _xn_move_to(self, state):
        for ticket in self:
            ticket.write({'stage_id': ticket._xn_get_stage(state).id})
        return True

    def _xn_check_it_user(self):
        if not self.env.user.has_group('helpdesk_mgmt.group_helpdesk_user_own'):
            raise AccessError(_("Only the IT team can do this."))

    def _xn_check_requester_or_it(self):
        for ticket in self:
            if not (ticket.xn_is_it_user or ticket.xn_is_requester):
                raise AccessError(_(
                    "Only the employee who raised %s or the IT team can do this.",
                    ticket.number))

    def _xn_it_team_partners(self):
        """Who hears about new tickets: the ticket's team, or every Helpdesk
        user when the ticket has no team or the team has no members."""
        self.ensure_one()
        users = self.team_id.user_ids
        if not users:
            users = self.env.ref('helpdesk_mgmt.group_helpdesk_user').users
        return users.filtered(lambda u: u.active and not u.share).partner_id

    def _xn_ticket_url(self):
        self.ensure_one()
        return '%s/mail/view?model=%s&res_id=%s' % (
            self.get_base_url(), self._name, self.id)

    def _xn_send_template(self, xmlid):
        """Queue an email to the requester. send_mail only queues it, so a
        broken mail server cannot stop the ticket being saved."""
        template = self.env.ref(xmlid, raise_if_not_found=False)
        if not template:
            _logger.warning("Mail template %s is missing", xmlid)
            return
        for ticket in self.filtered('partner_id'):
            template.send_mail(
                ticket.id, email_layout_xmlid='mail.mail_notification_light')

    def _xn_notify_it_team(self):
        for ticket in self:
            partners = ticket._xn_it_team_partners() - self.env.user.partner_id
            if not partners:
                continue
            body = Markup(
                "<p>A new IT ticket has been raised.</p>"
                "<ul>"
                "<li><b>Ticket:</b> %s</li>"
                "<li><b>Subject:</b> %s</li>"
                "<li><b>Raised by:</b> %s</li>"
                "<li><b>Category:</b> %s</li>"
                "<li><b>Priority:</b> %s</li>"
                "</ul>"
                "<p><a href=\"%s\">Open %s</a></p>"
            ) % (
                ticket.number, ticket.name,
                ticket.xn_employee_id.name or ticket.partner_name or '',
                ticket.category_id.complete_name or '-',
                dict(ticket._fields['priority']._description_selection(self.env)).get(
                    ticket.priority, ''),
                ticket._xn_ticket_url(), ticket.number,
            )
            ticket.message_notify(
                partner_ids=partners.ids,
                subject=_("New IT ticket %(number)s: %(subject)s",
                          number=ticket.number, subject=ticket.name),
                body=body,
                email_layout_xmlid='mail.mail_notification_layout',
            )

    # ---------------------------------------------------------------------
    # Buttons
    # ---------------------------------------------------------------------

    def action_xn_in_progress(self):
        self._xn_check_it_user()
        return self._xn_move_to('in_progress')

    def action_xn_on_hold(self):
        self._xn_check_it_user()
        return self._xn_move_to('on_hold')

    def action_xn_resolve(self):
        self._xn_check_it_user()
        return self._xn_move_to('resolved')

    def action_xn_close(self):
        self._xn_check_it_user()
        return self._xn_move_to('closed')

    def action_xn_confirm_resolution(self):
        """The requester agrees the issue is fixed: Resolved -> Closed."""
        self._xn_check_requester_or_it()
        for ticket in self:
            if ticket.stage_id.xn_state != 'resolved':
                raise UserError(_("Only a resolved ticket can be confirmed."))
            # sudo: employees have no write access on tickets. The tracking
            # message still records the real user as the author.
            ticket.sudo()._xn_move_to('closed')
            ticket.sudo().message_post(
                body=_("%s confirmed the resolution.", self.env.user.name),
                author_id=self.env.user.partner_id.id,
                message_type='comment', subtype_xmlid='mail.mt_comment')
        return True

    def action_xn_reopen(self):
        """The issue persists: back to In Progress (or New if unassigned)."""
        self._xn_check_requester_or_it()
        for ticket in self:
            if ticket.stage_id.xn_state not in XN_DONE_STATES:
                raise UserError(_("Only a resolved or closed ticket can be reopened."))
            target = 'in_progress' if ticket.user_id else 'new'
            ticket.sudo()._xn_move_to(target)
            ticket.sudo().message_post(
                body=_("%s reopened the ticket: the issue persists.", self.env.user.name),
                author_id=self.env.user.partner_id.id,
                message_type='comment', subtype_xmlid='mail.mt_comment')
        return True
