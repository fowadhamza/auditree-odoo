# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import date_utils, float_compare, format_date
from datetime import datetime, time
from pytz import timezone
import logging
import uuid

_logger = logging.getLogger(__name__)

LIMIT_PERIOD_LABELS = {
    'request': 'per request',
    'month': 'per month',
    'year': 'per year',
}


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    xn_limit_days = fields.Float(
        string='Max Days Allowed',
        help="Only for time off types that do not require an allocation. "
             "Caps how many days an employee can request in the chosen "
             "period. 0 means no limit.")
    xn_limit_period = fields.Selection(
        [('request', 'Per Request'),
         ('month', 'Per Month'),
         ('year', 'Per Year')],
        string='Limit Period', default='year', required=True)

    @api.constrains('xn_limit_days')
    def _xn_check_limit_days(self):
        for leave_type in self:
            if leave_type.xn_limit_days < 0:
                raise ValidationError(_("Max Days Allowed cannot be negative."))


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    # Odoo 17 only allows a half day on a single date. These add the two
    # multi-day patterns: a range that starts/ends at midday, and the same
    # half of every working day in a range.
    xn_start_half = fields.Boolean(string='First Day: Afternoon Only')
    xn_end_half = fields.Boolean(string='Last Day: Morning Only')
    xn_daily_half = fields.Boolean(string='Half Day on Each Day')
    xn_daily_period = fields.Selection(
        [('am', 'Morning'), ('pm', 'Afternoon')],
        string='Which Half', default='am')
    xn_daily_group = fields.Char(copy=False, index=True, readonly=True)
    xn_daily_group_info = fields.Char(
        string='Series', compute='_compute_xn_daily_group_info')
    xn_is_multi_day = fields.Boolean(compute='_compute_xn_is_multi_day')
    xn_daily_half_total = fields.Float(
        string='Duration', compute='_compute_xn_daily_half_total')

    @api.depends('xn_daily_half', 'employee_id', 'request_date_from', 'request_date_to')
    def _compute_xn_daily_half_total(self):
        for leave in self:
            if leave.xn_daily_half and leave.employee_id and leave.request_date_from:
                leave.xn_daily_half_total = 0.5 * len(self._xn_work_days(
                    leave.employee_id, leave.request_date_from,
                    leave.request_date_to or leave.request_date_from))
            else:
                leave.xn_daily_half_total = 0.0

    @api.model
    def _xn_work_days(self, employee, date_from, date_to):
        """Dates between date_from and date_to the employee works on and is
        not already off (public holidays and existing time off excluded)."""
        tz = timezone(employee.tz or self.env.user.tz or 'UTC')
        return [
            day for day, hours in employee.list_work_time_per_day(
                tz.localize(datetime.combine(date_from, time.min)),
                tz.localize(datetime.combine(date_to, time.max)))
            if hours
        ]

    @api.depends('request_date_from', 'request_date_to')
    def _compute_xn_is_multi_day(self):
        for leave in self:
            leave.xn_is_multi_day = bool(
                leave.request_date_from and leave.request_date_to
                and leave.request_date_to > leave.request_date_from)

    @api.depends('xn_daily_group')
    def _compute_xn_daily_group_info(self):
        for leave in self:
            if not leave.xn_daily_group:
                leave.xn_daily_group_info = False
                continue
            series = self.sudo().search(
                [('xn_daily_group', '=', leave.xn_daily_group)],
                order='request_date_from')
            leave.xn_daily_group_info = _(
                "%(count)s half days, %(first)s to %(last)s. Approving or "
                "refusing one applies to all of them.",
                count=len(series),
                first=format_date(self.env, series[:1].request_date_from),
                last=format_date(self.env, series[-1:].request_date_from),
            )

    @api.depends('request_date_from_period', 'request_hour_from', 'request_hour_to',
                 'request_date_from', 'request_date_to', 'request_unit_half',
                 'request_unit_hours', 'employee_id', 'xn_start_half', 'xn_end_half')
    def _compute_date_from_to(self):
        """Move the start / end of a multi-day request to midday when asked."""
        super()._compute_date_from_to()
        for leave in self:
            if (leave.request_unit_half or leave.request_unit_hours
                    or not leave.xn_is_multi_day
                    or not (leave.xn_start_half or leave.xn_end_half)):
                continue
            resource = leave.employee_id or leave
            if leave.xn_start_half:
                attendance, _dummy = leave._get_attendances(
                    leave.request_date_from, leave.request_date_from,
                    day_period='afternoon')
                leave.date_from = self._to_utc(
                    leave.request_date_from, attendance.hour_from, resource)
            if leave.xn_end_half:
                _dummy, attendance = leave._get_attendances(
                    leave.request_date_to, leave.request_date_to,
                    day_period='morning')
                leave.date_to = self._to_utc(
                    leave.request_date_to, attendance.hour_to, resource)

    @api.model_create_multi
    def create(self, vals_list):
        expanded = []
        for vals in vals_list:
            expanded.extend(self._xn_split_daily_half(vals))
        return super().create(expanded)

    @api.model
    def _xn_vals_employee(self, vals):
        """The single employee a create() vals dict is for, if there is one."""
        Employee = self.env['hr.employee']
        if vals.get('holiday_type', 'employee') != 'employee':
            return Employee
        if vals.get('employee_id'):
            return Employee.browse(vals['employee_id'])
        ids = []
        for command in vals.get('employee_ids') or []:
            if command[0] == 6:
                ids = list(command[2])
            elif command[0] == 4:
                ids.append(command[1])
        if ids:
            return Employee.browse(ids) if len(ids) == 1 else Employee
        if self.env.context.get('default_employee_id'):
            return Employee.browse(self.env.context['default_employee_id'])
        return self.env.user.employee_id

    @api.model
    def _xn_split_daily_half(self, vals):
        """Turn a "half day on each day" request into one half-day vals per
        working day of the employee, all sharing an xn_daily_group."""
        if not vals.get('xn_daily_half'):
            return [vals]
        date_from = fields.Date.to_date(vals.get('request_date_from'))
        date_to = fields.Date.to_date(vals.get('request_date_to')) or date_from
        if vals.get('request_unit_half') or vals.get('request_unit_hours') or not date_from:
            return [dict(vals, xn_daily_half=False)]
        employee = self._xn_vals_employee(vals)
        if len(employee) != 1:
            raise UserError(_("Half Day on Each Day can only be used for one employee at a time."))
        work_days = self._xn_work_days(employee, date_from, date_to)
        if not work_days:
            raise UserError(_("%(employee)s has no working days between %(start)s and %(end)s.",
                              employee=employee.name,
                              start=format_date(self.env, date_from),
                              end=format_date(self.env, date_to)))
        group = uuid.uuid4().hex if len(work_days) > 1 else False
        result = []
        for day in work_days:
            day_vals = dict(
                vals,
                request_date_from=day,
                request_date_to=day,
                request_unit_half=True,
                request_date_from_period=vals.get('xn_daily_period') or 'am',
                xn_daily_half=False,
                xn_start_half=False,
                xn_end_half=False,
                xn_daily_group=group,
            )
            # Let Odoo recompute these from the single day.
            for key in ('date_from', 'date_to', 'number_of_days', 'number_of_hours'):
                day_vals.pop(key, None)
            result.append(day_vals)
        return result

    def _xn_with_daily_siblings(self):
        """self plus the other requests of the same series in the same state."""
        groups = [group for group in self.mapped('xn_daily_group') if group]
        if not groups:
            return self
        siblings = self.sudo().search([
            ('xn_daily_group', 'in', groups),
            ('state', 'in', self.mapped('state')),
        ])
        return self | self.browse(siblings.ids)

    def action_approve(self, check_state=True):
        return super(HrLeave, self._xn_with_daily_siblings()).action_approve(check_state=check_state)

    def action_validate(self):
        return super(HrLeave, self._xn_with_daily_siblings()).action_validate()

    def action_refuse(self):
        return super(HrLeave, self._xn_with_daily_siblings()).action_refuse()

    @api.constrains('holiday_status_id', 'employee_id', 'number_of_days',
                    'request_date_from', 'state')
    def _xn_check_leave_type_limit(self):
        """Enforce the day cap set on time off types without allocation.

        Refused and archived (cancelled) requests do not count. For the month
        and year periods a request is counted in full against the period its
        start date falls in.
        """
        for leave in self:
            leave_type = leave.holiday_status_id
            if (leave_type.requires_allocation != 'no'
                    or leave_type.xn_limit_days <= 0
                    or leave.state == 'refuse'
                    or not leave.employee_id
                    or not leave.request_date_from):
                continue
            limit = leave_type.xn_limit_days
            period = leave_type.xn_limit_period
            if period == 'request':
                taken = leave.number_of_days
            else:
                start = date_utils.start_of(leave.request_date_from, period)
                end = date_utils.end_of(leave.request_date_from, period)
                others = self.sudo().search([
                    ('employee_id', '=', leave.employee_id.id),
                    ('holiday_status_id', '=', leave_type.id),
                    ('state', '!=', 'refuse'),
                    ('request_date_from', '>=', start),
                    ('request_date_from', '<=', end),
                ])
                taken = sum((others | leave).mapped('number_of_days'))
            if float_compare(taken, limit, precision_digits=2) > 0:
                raise ValidationError(_(
                    "%(type)s allows at most %(limit)s day(s) %(period)s. "
                    "This request would bring %(employee)s to %(taken)s day(s).",
                    type=leave_type.name,
                    limit='%g' % limit,
                    period=LIMIT_PERIOD_LABELS[period],
                    employee=leave.employee_id.name,
                    taken='%g' % round(taken, 2),
                ))
