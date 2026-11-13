# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

from odoo import models, fields, api, _

from .activity_settings import get_settings

_logger = logging.getLogger(__name__)

SLOT_MINUTES = 5
OUT_OF_HOURS_GRACE = 30   # minutes before start / after end of the schedule

STATUSES = [
    ('good', 'On Target'),
    ('fair', 'Below Target'),
    ('low', 'Under Half'),
    ('none', 'No Activity'),
]

DAY_KINDS = [
    ('working', 'Working Day'),
    ('weekend', 'Weekend'),
    ('holiday', 'Public Holiday'),
]


def _status(productive, screen, target):
    if not screen:
        return 'none'
    if target <= 0 or productive >= target:
        return 'good'
    if productive >= target / 2.0:
        return 'fair'
    return 'low'


class XnActivityDay(models.Model):
    """Stored daily summary: one row per person per local date.

    Recomputed from the slots by _xn_recompute() whenever slots arrive, an
    employee is linked, a category or department override changes, or a day
    note is added. Raw slots expire after the retention period; these rows
    are kept longer (summary retention).
    """
    _name = 'xn.activity.day'
    _description = 'Daily Work Metrics'
    _order = 'date desc, user_label'
    _rec_name = 'user_label'

    day_key = fields.Char(required=True, index=True, readonly=True)
    date = fields.Date(required=True, index=True, readonly=True)
    employee_id = fields.Many2one('hr.employee', readonly=True, index=True,
                                  ondelete='cascade')
    user_label = fields.Char(string='Employee / Sign-in', readonly=True)
    linked = fields.Boolean(readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    screen_hours = fields.Float(string='Screen Time', readonly=True,
                                group_operator='sum')
    productive_hours = fields.Float(string='Productive', readonly=True,
                                    group_operator='sum')
    work_hours = fields.Float(string='Work Time', readonly=True,
                              group_operator='sum',
                              help="Screen time minus time in Unproductive apps.")
    idle_hours = fields.Float(string='Idle', readonly=True,
                              group_operator='sum')
    locked_hours = fields.Float(string='Locked', readonly=True,
                                group_operator='sum')
    productive_status = fields.Selection(STATUSES, string='Target',
                                         readonly=True, index=True)
    first_activity = fields.Datetime(readonly=True)
    last_activity = fields.Datetime(readonly=True)
    day_kind = fields.Selection(DAY_KINDS, string='Schedule', readonly=True)
    out_of_hours = fields.Boolean(string='Out of Hours', readonly=True,
                                  help="Active outside the working schedule, "
                                       "or on a weekend or public holiday.")
    time_off = fields.Char(readonly=True)
    note = fields.Text(readonly=True)
    has_note = fields.Boolean(readonly=True, index=True)
    computers = fields.Char(readonly=True)

    _sql_constraints = [
        ('day_uniq', 'UNIQUE(day_key, date)', 'Duplicate daily row.'),
    ]

    # ------------------------------------------------------------------
    # Recompute
    # ------------------------------------------------------------------

    @api.model
    def _xn_recompute(self, pairs):
        """Rebuild the daily rows for an iterable of (day_key, date)."""
        pairs = {(k, fields.Date.to_date(d)) for k, d in pairs if k and d}
        if not pairs:
            return
        Day = self.sudo()
        self.env.flush_all()
        keys = [p[0] for p in pairs]
        dates = [p[1] for p in pairs]
        cr = self.env.cr
        cr.execute("""
            WITH wanted AS (
                SELECT * FROM unnest(%s::varchar[], %s::date[])
                    AS w(day_key, local_date)
            )
            SELECT s.day_key, s.local_date,
                   max(s.employee_id),
                   min(s.user_key),
                   COALESCE(sum(x.act), 0),
                   COALESCE(sum(x.idl), 0),
                   COALESCE(sum(s.locked_hours), 0),
                   COALESCE(sum(x.act) FILTER (
                       WHERE COALESCE(r.category, a.category) = 'productive'), 0),
                   COALESCE(sum(x.act) FILTER (
                       WHERE COALESCE(r.category, a.category) = 'unproductive'), 0),
                   min(s.slot_start) FILTER (WHERE x.act > 0),
                   max(s.slot_start) FILTER (WHERE x.act > 0),
                   min(s.local_minute) FILTER (WHERE x.act > 0),
                   max(s.local_minute) FILTER (WHERE x.act > 0),
                   string_agg(DISTINCT d.name, ', ')
              FROM xn_activity_slot s
              JOIN wanted w ON w.day_key = s.day_key
                           AND w.local_date = s.local_date
              JOIN xn_activity_app a ON a.id = s.app_id
              JOIN xn_activity_device d ON d.id = s.device_id
         LEFT JOIN hr_employee e ON e.id = s.employee_id
         LEFT JOIN xn_activity_app_rule r ON r.app_id = s.app_id
                                         AND r.department_id = e.department_id
              -- Apps marked "Count Idle as Active" (meetings, reading):
              -- their idle time is reported as active.
             CROSS JOIN LATERAL (SELECT
                   s.active_hours + CASE WHEN a.idle_as_active
                                         THEN s.idle_hours ELSE 0 END AS act,
                   CASE WHEN a.idle_as_active THEN 0
                        ELSE s.idle_hours END AS idl) x
          GROUP BY s.day_key, s.local_date
        """, (keys, dates))
        data = {}
        for row in cr.fetchall():
            data[(row[0], row[1])] = {
                'employee_id': row[2], 'user_key': row[3],
                'screen': row[4], 'idle': row[5], 'locked': row[6],
                'productive': row[7], 'unproductive': row[8],
                'first': row[9], 'last': row[10],
                'first_minute': row[11], 'last_minute': row[12],
                'computers': row[13] or '',
            }

        emp_ids = set()
        for key, _d in pairs:
            if key.startswith('emp:'):
                emp_ids.add(int(key[4:]))
        employees = self.env['hr.employee'].sudo().with_context(
            active_test=False).browse(emp_ids).exists()
        emp_by_id = {e.id: e for e in employees}

        notes = self._xn_notes(employees, dates)
        leaves = self._xn_time_off(employees, dates)
        schedule = self._xn_schedule(employees, dates)
        target = get_settings(self.env)['productive_target']

        existing = Day.search([('day_key', 'in', list(set(keys))),
                               ('date', 'in', list(set(dates)))])
        by_pair = {(d.day_key, d.date): d for d in existing}

        to_create = []
        to_unlink = Day.browse()
        for pair in pairs:
            key, date = pair
            row = data.get(pair)
            emp = emp_by_id.get(int(key[4:])) if key.startswith('emp:') else None
            note = notes.get((emp.id, date)) if emp else None
            current = by_pair.get(pair)
            if not row and not note:
                if current:
                    to_unlink |= current
                continue
            vals = self._xn_vals(key, date, row, emp, note,
                                 leaves, schedule, target)
            if current:
                current.write(vals)
            else:
                to_create.append(vals)
        if to_unlink:
            to_unlink.unlink()
        if to_create:
            Day.create(to_create)

    @api.model
    def _xn_vals(self, key, date, row, emp, note, leaves, schedule, target):
        row = row or {}
        screen = row.get('screen', 0.0)
        productive = row.get('productive', 0.0)
        last = row.get('last')
        kind, start_h, end_h = schedule.get(
            (emp.id, date) if emp else None, ('working', None, None))
        out_of_hours = False
        if screen:
            if kind != 'working':
                out_of_hours = True
            elif start_h is not None:
                first_m = row.get('first_minute')
                last_m = row.get('last_minute')
                if first_m is not None and \
                        first_m < start_h * 60 - OUT_OF_HOURS_GRACE:
                    out_of_hours = True
                if last_m is not None and \
                        last_m + SLOT_MINUTES > end_h * 60 + OUT_OF_HOURS_GRACE:
                    out_of_hours = True
        return {
            'day_key': key,
            'date': date,
            'employee_id': emp.id if emp else False,
            'linked': bool(emp),
            'user_label': emp.name if emp else (row.get('user_key') or key),
            'department_id': emp.department_id.id if emp else False,
            'screen_hours': screen,
            'productive_hours': productive,
            'work_hours': max(screen - row.get('unproductive', 0.0), 0.0),
            'idle_hours': row.get('idle', 0.0),
            'locked_hours': row.get('locked', 0.0),
            'productive_status': _status(productive, screen, target),
            'first_activity': row.get('first') or False,
            'last_activity': (last + timedelta(minutes=SLOT_MINUTES))
            if last else False,
            'computers': row.get('computers') or False,
            'day_kind': kind,
            'out_of_hours': out_of_hours,
            'time_off': leaves.get((emp.id, date)) if emp else False,
            'note': note or False,
            'has_note': bool(note),
        }

    @api.model
    def _xn_notes(self, employees, dates):
        if not employees:
            return {}
        notes = self.env['xn.activity.note'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('date', 'in', list(set(dates))),
        ], order='date, id')
        out = {}
        for n in notes:
            k = (n.employee_id.id, n.date)
            out[k] = (out[k] + '\n' + n.note) if k in out else n.note
        return out

    @api.model
    def _xn_time_off(self, employees, dates):
        """Approved leave per (employee id, date) -> 'Leave Type (half day)'."""
        if not employees:
            return {}
        lo, hi = min(dates), max(dates)
        leaves = self.env['hr.leave'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', hi),
            ('request_date_to', '>=', lo),
        ])
        out = {}
        for leave in leaves:
            label = leave.holiday_status_id.name or _('Time Off')
            if leave.request_unit_half:
                label = _('%s (half day)', label)
            elif leave.request_unit_hours:
                label = _('%s (hours)', label)
            d = leave.request_date_from
            while d <= leave.request_date_to:
                out[(leave.employee_id.id, d)] = label
                d += timedelta(days=1)
        return out

    @api.model
    def _xn_schedule(self, employees, dates):
        """(employee id, date) -> (kind, start hour, end hour)."""
        out = {}
        if not employees:
            return out
        lo, hi = min(dates), max(dates)
        holidays = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('date_from', '<=', datetime.combine(hi, time.max)),
            ('date_to', '>=', datetime.combine(lo, time.min)),
        ])
        for emp in employees:
            cal = emp.resource_calendar_id or emp.company_id.resource_calendar_id
            hours = {}
            if cal:
                for att in cal.attendance_ids:
                    if att.display_type or att.day_period == 'lunch':
                        continue
                    day = int(att.dayofweek)
                    s, e = hours.get(day, (24.0, 0.0))
                    hours[day] = (min(s, att.hour_from), max(e, att.hour_to))
            for d in set(dates):
                is_holiday = any(
                    (not h.calendar_id or h.calendar_id == cal)
                    and h.date_from.date() <= d <= h.date_to.date()
                    for h in holidays)
                if is_holiday:
                    out[(emp.id, d)] = ('holiday', None, None)
                elif cal and d.weekday() not in hours:
                    out[(emp.id, d)] = ('weekend', None, None)
                else:
                    s, e = hours.get(d.weekday(), (None, None))
                    out[(emp.id, d)] = ('working', s, e)
        return out

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------

    @api.model
    def _xn_recompute_for_apps(self, apps, department=None):
        """Recompute every day that has slots in `apps` (optionally only for
        employees of `department`), after a category change."""
        if not apps:
            return
        self.env.flush_all()
        if department:
            self.env.cr.execute("""
                SELECT DISTINCT s.day_key, s.local_date
                  FROM xn_activity_slot s
                  JOIN hr_employee e ON e.id = s.employee_id
                 WHERE s.app_id IN %s AND e.department_id = %s
            """, (tuple(apps.ids), department.id))
        else:
            self.env.cr.execute("""
                SELECT DISTINCT day_key, local_date
                  FROM xn_activity_slot WHERE app_id IN %s
            """, (tuple(apps.ids),))
        self._xn_recompute(self.env.cr.fetchall())

    @api.model
    def _xn_refresh_status(self):
        """Re-grade every row after the productive target changes."""
        target = get_settings(self.env)['productive_target']
        self.env.flush_all()
        self.env.cr.execute("""
            UPDATE xn_activity_day SET productive_status = CASE
                WHEN COALESCE(screen_hours, 0) = 0 THEN 'none'
                WHEN %(t)s <= 0 OR productive_hours >= %(t)s THEN 'good'
                WHEN productive_hours >= %(t)s / 2.0 THEN 'fair'
                ELSE 'low' END
        """, {'t': target})
        self.invalidate_model(['productive_status'])

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_open_slots(self):
        """That person's 5-minute slots for the day, grouped by app.

        Opening someone else's detail is logged (who viewed whom, when).
        """
        self.ensure_one()
        me = self.env.user
        if not self.employee_id or self.employee_id.user_id != me:
            self.env['xn.activity.view.log'].sudo().create({
                'viewer_id': me.id,
                'employee_id': self.employee_id.id,
                'user_label': self.user_label,
                'date': self.date,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': _('%(who)s - %(date)s', who=self.user_label,
                      date=self.date),
            'res_model': 'xn.activity.slot',
            'view_mode': 'tree,pivot,graph',
            'views': [
                (self.env.ref('xn_activity.view_xn_activity_slot_tree').id,
                 'tree'),
                (False, 'pivot'),
                (False, 'graph'),
            ],
            'domain': [('day_key', '=', self.day_key),
                       ('local_date', '=', self.date)],
            'context': {'group_by': ['app_id'], 'create': False},
        }

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------

    @api.model
    def _cron_purge(self):
        """Delete slots and summaries past their retention periods."""
        s = get_settings(self.env)
        today = fields.Date.context_today(self)
        raw_cut = today - timedelta(days=s['retention_days'])
        sum_cut = today - timedelta(days=s['summary_retention_days'])
        cr = self.env.cr
        cr.execute("DELETE FROM xn_activity_slot WHERE local_date < %s",
                   (raw_cut,))
        slots = cr.rowcount
        cr.execute("DELETE FROM xn_activity_day WHERE date < %s", (sum_cut,))
        days = cr.rowcount
        cr.execute("DELETE FROM xn_activity_view_log WHERE date < %s",
                   (sum_cut,))
        self.env.invalidate_all()
        _logger.info("xn_activity: purged %s slots before %s, %s days before %s",
                     slots, raw_cut, days, sum_cut)
