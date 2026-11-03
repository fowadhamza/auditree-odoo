# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

from .jl_step import PROCESSES

_logger = logging.getLogger(__name__)

TZ = 'Asia/Kolkata'
DONE = '1_done'
CANCELLED = '1_canceled'
CLOSED = (DONE, CANCELLED)


class WorkingDays:
    """Working-day arithmetic on a resource calendar.

    Working weekdays come from the calendar's attendances (Monday to Friday
    without one); public holidays are the calendar's global time off.
    """

    def __init__(self, env, calendar):
        self.env = env
        self.calendar = calendar
        days = calendar.attendance_ids.filtered(
            lambda a: not a.display_type).mapped('dayofweek') if calendar else []
        self.weekdays = {int(d) for d in days} or {0, 1, 2, 3, 4}
        self._holidays = None

    def _load_holidays(self, around):
        start = datetime.combine(around - timedelta(days=400), time.min)
        end = datetime.combine(around + timedelta(days=400), time.max)
        leaves = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('calendar_id', 'in', [self.calendar.id, False]),
            ('date_from', '<=', end),
            ('date_to', '>=', start),
        ])
        holidays = set()
        for leave in leaves:
            day = leave.date_from.date()
            while day <= leave.date_to.date():
                holidays.add(day)
                day += timedelta(days=1)
        self._holidays = holidays

    def is_working(self, day):
        if self._holidays is None:
            self._load_holidays(day)
        return day.weekday() in self.weekdays and day not in self._holidays

    def add(self, day, count):
        """The ``count``-th working day after ``day`` (before, if negative).

        ``count`` 0 returns ``day`` itself, working day or not.
        """
        step = 1 if count > 0 else -1
        remaining = abs(count)
        while remaining:
            day += timedelta(days=step)
            if self.is_working(day):
                remaining -= 1
        return day

    def between(self, start, end):
        """Working days after ``start`` up to and including ``end``."""
        count = 0
        day = start
        while day < end:
            day += timedelta(days=1)
            if self.is_working(day):
                count += 1
        return count


class XnJlChecklist(models.Model):
    _name = 'xn.jl.checklist'
    _description = 'Joiner/Leaver Checklist'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(compute='_compute_name', store=True)
    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, tracking=True,
        ondelete='restrict')
    company_id = fields.Many2one(
        'res.company', related='employee_id.company_id', store=True)
    manager_id = fields.Many2one(
        'hr.employee', string='Reporting Manager', related='employee_id.parent_id')
    process = fields.Selection(PROCESSES, required=True, default='join', readonly=True)
    date = fields.Date(
        required=True, tracking=True,
        help="Joining date for a joining checklist, last working day for an "
             "exit. Changing it moves every step dated from it.")
    exit_type = fields.Selection([
        ('resignation', 'Resignation'),
        ('termination', 'Termination'),
        ('immediate', 'Immediate termination'),
    ], tracking=True,
        help="Immediate termination: steps are due today and disabling access "
             "is alerted the same evening.")
    bond_required = fields.Boolean(
        default=True, tracking=True,
        help="Clear only when Management confirms no bond is needed.")
    state = fields.Selection([
        ('running', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='running', required=True, tracking=True)
    note = fields.Text()
    task_ids = fields.One2many('project.task', 'xn_jl_checklist_id', string='Steps')
    task_count = fields.Integer(compute='_compute_counts')
    open_count = fields.Integer(string='Open Steps', compute='_compute_counts')
    late_count = fields.Integer(string='Late Steps', compute='_compute_counts')

    @api.depends('employee_id', 'process')
    def _compute_name(self):
        labels = dict(PROCESSES)
        for rec in self:
            rec.name = '%s - %s' % (labels.get(rec.process, ''), rec.employee_id.name or '')

    def _compute_counts(self):
        today = self._xn_today()
        for rec in self:
            tasks = rec.sudo().with_context(active_test=False).task_ids
            open_tasks = tasks.filtered(lambda t: t.state not in CLOSED)
            rec.task_count = len(tasks)
            rec.open_count = len(open_tasks)
            rec.late_count = len(open_tasks.filtered(
                lambda t: t.xn_jl_due_date and t.xn_jl_due_date < today))

    @api.constrains('employee_id', 'process', 'state')
    def _check_one_running(self):
        for rec in self.filtered(lambda r: r.state == 'running'):
            if self.search_count([
                ('id', '!=', rec.id),
                ('employee_id', '=', rec.employee_id.id),
                ('process', '=', rec.process),
                ('state', '=', 'running'),
            ]):
                raise ValidationError(_(
                    "%s already has a %s checklist in progress.",
                    rec.employee_id.name, dict(PROCESSES)[rec.process].lower()))

    @api.constrains('process', 'exit_type')
    def _check_exit_type(self):
        for rec in self:
            if rec.process == 'leave' and not rec.exit_type:
                raise ValidationError(_("Choose whether the exit is a resignation "
                                        "or a termination."))

    # -- Dates ------------------------------------------------------------

    @api.model
    def _xn_today(self):
        return fields.Date.context_today(self.with_context(tz=TZ))

    def _xn_working_days(self):
        company = self.company_id or self.env.company
        return WorkingDays(self.env, company.resource_calendar_id)

    def _xn_due(self, step, start, wd, done_on=None):
        """Due date of ``step`` in this checklist, never before ``start``.

        ``done_on`` is when the step it follows was done; an 'after' step
        without it has no due date yet.
        """
        if step.anchor == 'after':
            if not done_on:
                return False
            return max(wd.add(done_on, step.days), start)
        if self.exit_type == 'immediate':
            return start
        if step.anchor == 'date':
            due = wd.add(self.date, step.days)
        else:
            due = wd.add(start, step.days)
        return max(due, start)

    @staticmethod
    def _xn_deadline(day):
        # Noon keeps the deadline on the same calendar day in any timezone.
        return datetime.combine(day, time(12, 0)) if day else False

    # -- Steps ------------------------------------------------------------

    def _xn_steps(self):
        self.ensure_one()
        steps = self.env['xn.jl.step'].search([('process', '=', self.process)])
        if self.process == 'leave':
            kind = 'resignation' if self.exit_type == 'resignation' else 'termination'
            steps = steps.filtered(lambda s: s.exit_types in ('all', kind))
        if not self.bond_required:
            steps = steps.filtered(lambda s: s.condition != 'bond')
        return steps

    def _xn_owner(self, step):
        Role = self.env['xn.jl.role']
        if step.role == 'manager':
            user = self.employee_id.parent_id.user_id
        else:
            user = Role._xn_user(step.role)
        return user or Role._xn_user('hr') or self.env.user

    def _xn_task_vals(self, step, due):
        description = ''
        if step.note:
            description += '<p>%s</p>' % step.note
        if step.proof_required:
            description += '<p><b>%s</b> %s</p>' % (_('Proof:'), step.proof_required)
        if step.external:
            description += '<p>%s</p>' % _(
                "Waits on someone outside Auditree: chase it; it is not escalated.")
        return {
            'name': '%s - %s' % (step.name, self.employee_id.name),
            'project_id': self.env.ref('xn_joiner_leaver.project_joiner_leaver').id,
            'company_id': self.company_id.id or self.env.company.id,
            'user_ids': [(6, 0, self._xn_owner(step).ids)],
            'date_deadline': self._xn_deadline(due),
            'description': description,
            'xn_jl_checklist_id': self.id,
            'xn_jl_step_id': step.id,
            'xn_jl_due_date': due,
        }

    def _xn_generate_tasks(self):
        """Create one task per applicable step.

        A step that follows a step this checklist does not have (e.g. a
        bond step that was skipped) is dated from the start instead.
        """
        Task = self.env['project.task'].sudo().with_context(
            mail_create_nolog=True, mail_auto_subscribe_no_notify=True)
        today = self._xn_today()
        for rec in self:
            wd = rec._xn_working_days()
            steps = rec._xn_steps()
            vals_list = []
            for step in steps:
                if step.anchor == 'after' and step.after_step_id not in steps:
                    due = rec._xn_due(step, today, wd, done_on=today)
                else:
                    due = rec._xn_due(step, today, wd)
                vals_list.append(rec._xn_task_vals(step, due))
            tasks = Task.create(vals_list)
            rec._xn_grant_project_access(tasks.user_ids)
            _logger.info("xn_joiner_leaver: %s steps created for %s",
                         len(tasks), rec.name)

    def _xn_grant_project_access(self, users):
        """Owners need Project > User to open their steps."""
        group = self.env.ref('project.group_project_user')
        missing = users.filtered(lambda u: not u.share and group not in u.groups_id)
        if missing:
            missing.sudo().write({'groups_id': [(4, group.id)]})
            self.message_post(body=_(
                "Given Project access so they can see their steps: %s",
                ', '.join(missing.mapped('name'))))

    def _xn_reschedule(self):
        """Move the open steps dated from the joining date / last working day."""
        today = self._xn_today()
        for rec in self:
            wd = rec._xn_working_days()
            tasks = rec.sudo().task_ids.filtered(
                lambda t: t.state not in CLOSED and t.xn_jl_step_id.anchor == 'date')
            for task in tasks:
                due = rec._xn_due(task.xn_jl_step_id, today, wd)
                task.sudo().write({
                    'xn_jl_due_date': due,
                    'date_deadline': rec._xn_deadline(due),
                    'xn_jl_escalated': False,
                    'xn_jl_alerted': False,
                })

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._xn_generate_tasks()
        return records

    def write(self, vals):
        if 'date' in vals and any(r.state != 'running' for r in self):
            raise UserError(_("Only a checklist in progress can be re-dated."))
        res = super().write(vals)
        if 'date' in vals or vals.get('exit_type') == 'immediate':
            self._xn_reschedule()
        return res

    def _xn_check_complete(self):
        for rec in self.filtered(lambda r: r.state == 'running'):
            if rec.task_ids and all(t.state in CLOSED for t in rec.task_ids):
                rec.state = 'done'

    # -- Buttons ----------------------------------------------------------

    def action_cancel(self):
        """The joiner did not join, or the resignation was withdrawn."""
        for rec in self:
            open_tasks = rec.sudo().task_ids.filtered(lambda t: t.state not in CLOSED)
            open_tasks.sudo().with_context(xn_jl_cancelling=True).write(
                {'state': CANCELLED})
            rec.state = 'cancelled'

    def action_view_tasks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'xn_joiner_leaver.action_xn_jl_tasks')
        action['domain'] = [('xn_jl_checklist_id', '=', self.id)]
        action['context'] = {'search_default_open': 1}
        return action
