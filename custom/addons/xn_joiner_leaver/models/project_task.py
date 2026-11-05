# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from email.utils import formataddr

from odoo import models, fields, api, _
from odoo.exceptions import UserError

from .jl_checklist import CLOSED, DONE

_logger = logging.getLogger(__name__)

DEFAULT_FROM = 'hr@auditree.com'


class ProjectTask(models.Model):
    _inherit = 'project.task'

    xn_jl_checklist_id = fields.Many2one(
        'xn.jl.checklist', string='Joiner/Leaver Checklist', index=True,
        ondelete='cascade', copy=False)
    xn_jl_step_id = fields.Many2one(
        'xn.jl.step', string='Checklist Step', ondelete='restrict', copy=False)
    xn_jl_employee_id = fields.Many2one(
        'hr.employee', string='Joiner/Leaver', related='xn_jl_checklist_id.employee_id',
        store=True)
    xn_jl_process = fields.Selection(related='xn_jl_checklist_id.process', store=True)
    xn_jl_due_date = fields.Date(
        string='Step Due', index=True, copy=False, tracking=True,
        help="Empty until the step this one follows is done.")
    xn_jl_external = fields.Boolean(related='xn_jl_step_id.external')
    xn_jl_proof_required = fields.Char(related='xn_jl_step_id.proof_required')
    xn_jl_has_proof = fields.Boolean(
        string='Proof Attached', compute='_compute_xn_jl_has_proof')
    xn_jl_escalated = fields.Boolean(string='Escalated', copy=False)
    xn_jl_alerted = fields.Boolean(copy=False)

    def _compute_xn_jl_has_proof(self):
        ids = [i for i in self.ids if isinstance(i, int)]
        rows = self.env['ir.attachment'].sudo()._read_group(
            [('res_model', '=', 'project.task'), ('res_id', 'in', ids)],
            ['res_id']) if ids else []
        with_proof = {res_id for (res_id,) in rows}
        for task in self:
            task.xn_jl_has_proof = task.id in with_proof

    def _xn_jl_after_create(self):
        """Hook for modules acting on new checklist steps (helpdesk ticket)."""
        return True

    # -- Closing ----------------------------------------------------------

    def write(self, vals):
        new_state = vals.get('state')
        closing = self.browse()
        if new_state in CLOSED:
            closing = self.filtered(
                lambda t: t.xn_jl_checklist_id and t.state not in CLOSED)
            if new_state == DONE and not self.env.su:
                for task in closing.filtered('xn_jl_proof_required'):
                    if not task.xn_jl_has_proof:
                        raise UserError(_(
                            "Attach the proof (%(proof)s) to \"%(task)s\" before "
                            "marking it done.",
                            proof=task.xn_jl_proof_required, task=task.name))
        res = super().write(vals)
        # sudo: the project is private, so the user closing a step only sees
        # their own steps, not the ones that follow it.
        if closing and not self.env.context.get('xn_jl_cancelling'):
            closing.sudo()._xn_jl_schedule_next()
        if closing:
            closing.sudo().xn_jl_checklist_id._xn_check_complete()
        return res

    def _xn_jl_schedule_next(self):
        """Date the steps that follow the ones just closed."""
        checklists = self.xn_jl_checklist_id
        today = checklists._xn_today()
        for checklist in checklists:
            done_steps = self.filtered(
                lambda t: t.xn_jl_checklist_id == checklist).xn_jl_step_id
            waiting = checklist.task_ids.filtered(
                lambda t: t.state not in CLOSED and not t.xn_jl_due_date
                and t.xn_jl_step_id.after_step_id in done_steps)
            if not waiting:
                continue
            wd = checklist._xn_working_days()
            for task in waiting:
                due = checklist._xn_due(task.xn_jl_step_id, today, wd, done_on=today)
                task.sudo().write({
                    'xn_jl_due_date': due,
                    'date_deadline': checklist._xn_deadline(due),
                })

    # -- Reminders and escalation -----------------------------------------

    @api.model
    def _xn_jl_email_from(self):
        email = self.env['ir.config_parameter'].sudo().get_param(
            'xn_joiner_leaver.email_from') or DEFAULT_FROM
        return formataddr((_('Auditree HR'), email))

    @api.model
    def _xn_jl_send(self, partners, subject, template, values):
        if not partners:
            return
        values = dict(values, base_url=self.get_base_url())
        body = self.env['ir.qweb']._render(template, values)
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'email_from': self._xn_jl_email_from(),
            'recipient_ids': [(6, 0, partners.ids)],
            'body_html': body,
            'auto_delete': True,
        })

    @api.model
    def _xn_jl_open_tasks(self):
        return self.sudo().search([
            ('xn_jl_checklist_id.state', '=', 'running'),
            ('state', 'not in', CLOSED),
            ('xn_jl_due_date', '!=', False),
        ])

    def _xn_jl_rows(self, today, wd):
        rows = []
        for task in self.sorted(lambda t: (t.xn_jl_due_date, t.id)):
            rows.append({
                'task': task,
                'due': task.xn_jl_due_date,
                'late': wd.between(task.xn_jl_due_date, today)
                if task.xn_jl_due_date < today else 0,
                'owners': ', '.join(task.user_ids.mapped('name')),
            })
        return rows

    def _xn_jl_is_escalated(self, today, wd):
        self.ensure_one()
        if self.xn_jl_external or self.xn_jl_due_date >= today:
            return False
        late = wd.between(self.xn_jl_due_date, today)
        return late >= max(self.xn_jl_step_id.escalate_after, 1)

    @api.model
    def _xn_cron_jl_digest(self):
        """Morning digest: each owner's due and late steps, and the escalated
        steps to the Operations Manager.

        Sent on working days only. Escalated steps stay in the Operations
        Manager's digest every day until they are done.
        """
        Checklist = self.env['xn.jl.checklist']
        today = Checklist._xn_today()
        wd = Checklist._xn_working_days()
        if not wd.is_working(today):
            return
        tasks = self._xn_jl_open_tasks().filtered(lambda t: t.xn_jl_due_date <= today)
        by_user = defaultdict(lambda: self.browse())
        for task in tasks:
            for user in task.user_ids:
                by_user[user] |= task
        for user, user_tasks in by_user.items():
            self._xn_jl_send(
                user.partner_id,
                _("Joiner/leaver steps due - %s", today.strftime('%d %b %Y')),
                'xn_joiner_leaver.mail_body_digest',
                {'rows': user_tasks._xn_jl_rows(today, wd), 'user': user,
                 'escalation': False})
        escalated = tasks.filtered(lambda t: t._xn_jl_is_escalated(today, wd))
        escalated.filtered(lambda t: not t.xn_jl_escalated).write({'xn_jl_escalated': True})
        ops = self.env['xn.jl.role']._xn_user('ops')
        if escalated and ops:
            self._xn_jl_send(
                ops.partner_id,
                _("Late joiner/leaver steps - %s", today.strftime('%d %b %Y')),
                'xn_joiner_leaver.mail_body_digest',
                {'rows': escalated._xn_jl_rows(today, wd), 'user': ops,
                 'escalation': True})
        _logger.info("xn_joiner_leaver: digest to %s owners, %s escalated steps",
                     len(by_user), len(escalated))

    @api.model
    def _xn_cron_jl_urgent(self):
        """Evening alert for urgent steps (disabling access) still open on
        their due date. Sent once per step, to the owner and the Operations
        Manager."""
        Checklist = self.env['xn.jl.checklist']
        today = Checklist._xn_today()
        tasks = self._xn_jl_open_tasks().filtered(
            lambda t: t.xn_jl_step_id.urgent and not t.xn_jl_alerted
            and t.xn_jl_due_date <= today)
        if not tasks:
            return
        wd = Checklist._xn_working_days()
        ops = self.env['xn.jl.role']._xn_user('ops')
        for task in tasks:
            partners = task.user_ids.partner_id | ops.partner_id
            self._xn_jl_send(
                partners,
                _("Not done today: %s", task.name),
                'xn_joiner_leaver.mail_body_urgent',
                {'rows': task._xn_jl_rows(today, wd), 'task': task})
            task.message_post(
                body=_("Still open on the evening of its due date: alert sent to "
                       "%s.", ', '.join(partners.mapped('name'))),
                message_type='comment', subtype_xmlid='mail.mt_note')
        tasks.write({'xn_jl_alerted': True, 'xn_jl_escalated': True})
