# -*- coding: utf-8 -*-
import logging
from datetime import datetime, time, timedelta

import pytz

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
    # Not graded: the day is still going, or no work was expected.
    ('pending', 'In Progress'),
    ('weekend', 'Weekend'),
    ('holiday', 'Holiday'),
    ('leave', 'On Leave'),
]

LEAVE_KINDS = [
    ('full', 'Full Day'),
    ('half', 'Half Day'),
    ('hours', 'Hours'),
]

DAY_KINDS = [
    ('working', 'Working Day'),
    ('weekend', 'Weekend'),
    ('holiday', 'Public Holiday'),
]

# Columns _xn_write_rows() sets, with their SQL types: every key _xn_vals()
# returns except day_key and date, which identify the row.
_UPDATE_COLUMNS = [
    ('employee_id', 'int4'),
    ('linked', 'bool'),
    ('user_label', 'varchar'),
    ('department_id', 'int4'),
    ('screen_hours', 'float8'),
    ('productive_hours', 'float8'),
    ('work_hours', 'float8'),
    ('idle_hours', 'float8'),
    ('locked_hours', 'float8'),
    ('productive_status', 'varchar'),
    ('first_activity', 'timestamp'),
    ('last_activity', 'timestamp'),
    ('computers', 'varchar'),
    ('day_kind', 'varchar'),
    ('out_of_hours', 'bool'),
    ('time_off', 'varchar'),
    ('leave_kind', 'varchar'),
    ('leave_hours', 'float8'),
    ('target_hours', 'float8'),
    ('note', 'text'),
    ('has_note', 'bool'),
]
UPDATE_CHUNK = 1000


def _day_target(target, kind, leave_kind, leave_hours):
    """The productive target for one day: none on weekends, holidays and
    full-day leave, half on half-day leave, less the hours of hourly leave."""
    if kind in ('weekend', 'holiday') or leave_kind == 'full':
        return 0.0
    if leave_kind == 'half':
        return target / 2.0
    if leave_kind == 'hours':
        return max(target - (leave_hours or 0.0), 0.0)
    return target


def _status(productive, screen, day_target, kind, leave_kind, pending):
    """Keep in step with the SQL in _xn_refresh_status()."""
    if kind == 'holiday':
        return 'holiday'
    if kind == 'weekend':
        return 'weekend'
    if leave_kind == 'full':
        return 'leave'
    if pending:
        return 'pending'
    if not screen:
        return 'none'
    if day_target <= 0 or productive >= day_target:
        return 'good'
    if productive >= day_target / 2.0:
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
    productive_status = fields.Selection(
        STATUSES, string='Target', readonly=True, index=True,
        help="Productive time against the day's target. Today shows In "
             "Progress until the day is over; weekends, public holidays and "
             "full-day leave are not graded.")
    target_hours = fields.Float(
        string='Day Target', readonly=True,
        help="The daily productive target for this day: none on weekends, "
             "holidays and full-day leave, half on half-day leave, less the "
             "hours of hourly leave.")
    leave_kind = fields.Selection(LEAVE_KINDS, readonly=True)
    leave_hours = fields.Float(readonly=True)
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
        today = self._xn_today()

        existing = Day.search([('day_key', 'in', list(set(keys))),
                               ('date', 'in', list(set(dates)))])
        by_pair = {(d.day_key, d.date): d for d in existing}

        # Summaries outlive the 5-minute data (summary retention > slot
        # retention). A day before the oldest slot still stored has lost its
        # slots to the purge, so its metrics cannot be rebuilt: rebuilding it
        # would zero them (day with a note) or delete the row (no note).
        # Such days only take note changes. The purge cuts by date for
        # everyone, so min(local_date) is exactly where the slots end.
        cr.execute("SELECT min(local_date) FROM xn_activity_slot")
        slots_from = cr.fetchone()[0]

        to_create = []
        to_update = []
        to_unlink = Day.browse()
        for pair in pairs:
            key, date = pair
            row = data.get(pair)
            emp = emp_by_id.get(int(key[4:])) if key.startswith('emp:') else None
            note = notes.get((emp.id, date)) if emp else None
            current = by_pair.get(pair)
            frozen = not row and (slots_from is None or date < slots_from)
            if frozen and current:
                if (current.note or False) != (note or False):
                    current.write({'note': note or False,
                                   'has_note': bool(note)})
                continue
            if not row and not note:
                if current:
                    to_unlink |= current
                continue
            vals = self._xn_vals(key, date, row, emp, note,
                                 leaves, schedule, target, today)
            if current:
                to_update.append((current.id, vals))
            else:
                to_create.append(vals)
        self._xn_write_rows(to_update)
        if to_unlink:
            to_unlink.unlink()
        self._xn_insert_rows(to_create)

    @api.model
    def _xn_insert_rows(self, creates):
        """Batched INSERT of new day rows: [vals from _xn_vals].

        Two requests can rebuild the same new day at once (a person with two
        laptops posting at the same 5-minute mark). With the ORM, the second
        create failed on UNIQUE(day_key, date) and the request ended in a
        500. ON CONFLICT turns that into a serialization failure under
        Odoo's REPEATABLE READ, which Odoo retries: the retry sees the row
        and updates it.
        """
        if not creates:
            return
        cr = self.env.cr
        cols = ['day_key', 'date'] + [c for c, _t in _UPDATE_COLUMNS]
        types = ['varchar', 'date'] + [t for _c, t in _UPDATE_COLUMNS]
        tpl = '(' + ','.join('%s::' + t for t in types) \
            + ',%s::int4,%s::timestamp,%s::int4,%s::timestamp)'
        now = fields.Datetime.now()
        set_sql = ', '.join('%s = EXCLUDED.%s' % (c, c) for c in cols[2:])
        for i in range(0, len(creates), UPDATE_CHUNK):
            values = []
            for vals in creates[i:i + UPDATE_CHUNK]:
                params = []
                for col, typ in zip(cols, types):
                    v = vals[col]
                    if v is False and typ != 'bool':
                        v = None
                    params.append(v)
                params += [self.env.uid, now, self.env.uid, now]
                values.append(cr.mogrify(tpl, params).decode())
            cr.execute(
                "INSERT INTO xn_activity_day (" + ', '.join(cols)
                + ", create_uid, create_date, write_uid, write_date) VALUES "
                + ','.join(values)
                + " ON CONFLICT (day_key, date) DO UPDATE SET " + set_sql
                + ", write_uid = EXCLUDED.write_uid"
                + ", write_date = EXCLUDED.write_date",
                log_exceptions=False)   # a clash is retried, not a fault
        self.invalidate_model()

    @api.model
    def _xn_write_rows(self, updates):
        """Batched UPDATE of existing day rows: [(id, vals from _xn_vals)].

        A category change can rebuild thousands of days in one request, and
        one ORM write per row was slow enough to hit the request time limit.
        These are plain stored columns (no computes depend on them, no
        tracking), so writing them in SQL skips nothing.
        """
        if not updates:
            return
        cr = self.env.cr
        cols = [c for c, _t in _UPDATE_COLUMNS]
        tpl = '(' + ','.join(['%s::int4'] + ['%s::' + t
                                             for _c, t in _UPDATE_COLUMNS]) + ')'
        # Inlined (mogrify) so that a '%' inside a note is not taken for a
        # placeholder: the statement is executed without parameters.
        write_uid = cr.mogrify('%s', (self.env.uid,)).decode()
        write_date = cr.mogrify('%s', (fields.Datetime.now(),)).decode()
        set_sql = ', '.join('%s = v.%s' % (c, c) for c in cols)
        for i in range(0, len(updates), UPDATE_CHUNK):
            values = []
            for rec_id, vals in updates[i:i + UPDATE_CHUNK]:
                params = [rec_id]
                for col, typ in _UPDATE_COLUMNS:
                    v = vals[col]
                    if v is False and typ != 'bool':
                        v = None
                    params.append(v)
                values.append(cr.mogrify(tpl, params).decode())
            cr.execute(
                "UPDATE xn_activity_day d SET " + set_sql
                + ", write_uid = " + write_uid
                + ", write_date = " + write_date
                + " FROM (VALUES " + ','.join(values) + ") AS v(id, "
                + ', '.join(cols) + ") WHERE d.id = v.id")
        self.invalidate_model(cols + ['write_uid', 'write_date'])

    @api.model
    def _xn_vals(self, key, date, row, emp, note, leaves, schedule, target,
                 today):
        row = row or {}
        leave = leaves.get((emp.id, date)) if emp else None
        leave_kind = leave['kind'] if leave else False
        leave_hours = leave['hours'] if leave else 0.0
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
        day_target = _day_target(target, kind, leave_kind, leave_hours)
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
            'productive_status': _status(productive, screen, day_target, kind,
                                         leave_kind, date >= today),
            'target_hours': day_target,
            'leave_kind': leave_kind,
            'leave_hours': leave_hours,
            'first_activity': row.get('first') or False,
            'last_activity': (last + timedelta(minutes=SLOT_MINUTES))
            if last else False,
            'computers': row.get('computers') or False,
            'day_kind': kind,
            'out_of_hours': out_of_hours,
            'time_off': leave['label'] if leave else False,
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
        """Approved leave per (employee id, date) ->
        {'label': 'Leave Type (half day)', 'kind': full|half|hours,
         'hours': hours of hourly leave}. Two leaves on one day add up: two
        half days make a full day, hourly leave adds its hours."""
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
                label, kind, hours = _('%s (half day)', label), 'half', 0.0
            elif leave.request_unit_hours:
                label, kind, hours = (_('%s (hours)', label), 'hours',
                                      leave.number_of_hours or 0.0)
            else:
                kind, hours = 'full', 0.0
            d = leave.request_date_from
            while d <= leave.request_date_to:
                k = (leave.employee_id.id, d)
                prev = out.get(k)
                if prev:
                    kinds = {prev['kind'], kind}
                    if 'full' in kinds or kinds == {'half'}:
                        new_kind = 'full'
                    elif 'half' in kinds:
                        new_kind = 'half'    # half + hours: grade as half
                    else:
                        new_kind = 'hours'
                    out[k] = {'label': prev['label'] + ', ' + label,
                              'kind': new_kind,
                              'hours': prev['hours'] + hours}
                else:
                    out[k] = {'label': label, 'kind': kind, 'hours': hours}
                d += timedelta(days=1)
        return out

    @api.model
    def _xn_today(self):
        """Today in the company's working-time zone: the day that is still
        going and shows In Progress."""
        cal = self.env.company.resource_calendar_id
        tz = pytz.timezone((cal and cal.tz) or self.env.user.tz or 'UTC')
        return datetime.now(tz).date()

    @api.model
    def _xn_schedule(self, employees, dates):
        """(employee id, date) -> (kind, start hour, end hour)."""
        out = {}
        if not employees:
            return out
        lo, hi = min(dates), max(dates)
        # Stored in UTC: widen by a day each way, then compare local dates.
        holidays = self.env['resource.calendar.leaves'].sudo().search([
            ('resource_id', '=', False),
            ('date_from', '<=', datetime.combine(hi + timedelta(days=1),
                                                 time.max)),
            ('date_to', '>=', datetime.combine(lo - timedelta(days=1),
                                               time.min)),
        ])
        by_tz = {}

        def holiday_dates(tz_name):
            """[(calendar, first local date, last local date)]. A holiday on
            26 Jan IST is stored from 25 Jan 18:30 UTC: taking .date() of the
            UTC value would make 25 Jan a holiday too."""
            if tz_name not in by_tz:
                tz = pytz.timezone(tz_name)
                by_tz[tz_name] = [
                    (h.calendar_id,
                     pytz.utc.localize(h.date_from).astimezone(tz).date(),
                     pytz.utc.localize(h.date_to).astimezone(tz).date())
                    for h in holidays]
            return by_tz[tz_name]

        for emp in employees:
            cal = emp.resource_calendar_id or emp.company_id.resource_calendar_id
            local_holidays = holiday_dates((cal and cal.tz) or emp.tz or 'UTC')
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
                    (not h_cal or h_cal == cal) and h_from <= d <= h_to
                    for h_cal, h_from, h_to in local_holidays)
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
    def _xn_refresh_status(self, only_pending=False):
        """Re-grade rows from their stored columns: every row after the
        productive target changes, or (only_pending) the In Progress rows
        whose day is over. Same rules as _day_target() and _status()."""
        target = get_settings(self.env)['productive_target']
        self.env.flush_all()
        where = ("WHERE productive_status = 'pending' AND date < %(today)s"
                 if only_pending else "")
        self.env.cr.execute("""
            WITH g AS (
                SELECT id, CASE
                    WHEN day_kind IN ('weekend', 'holiday')
                      OR leave_kind = 'full' THEN 0.0
                    WHEN leave_kind = 'half' THEN %(t)s / 2.0
                    WHEN leave_kind = 'hours'
                      THEN GREATEST(%(t)s - COALESCE(leave_hours, 0), 0)
                    ELSE %(t)s END AS dt
                  FROM xn_activity_day """ + where + """
            )
            UPDATE xn_activity_day d SET target_hours = g.dt,
                   productive_status = CASE
                WHEN d.day_kind = 'holiday' THEN 'holiday'
                WHEN d.day_kind = 'weekend' THEN 'weekend'
                WHEN d.leave_kind = 'full' THEN 'leave'
                WHEN d.date >= %(today)s THEN 'pending'
                WHEN COALESCE(d.screen_hours, 0) = 0 THEN 'none'
                WHEN g.dt <= 0 OR d.productive_hours >= g.dt THEN 'good'
                WHEN d.productive_hours >= g.dt / 2.0 THEN 'fair'
                ELSE 'low' END
              FROM g WHERE d.id = g.id
        """, {'t': target, 'today': self._xn_today()})
        count = self.env.cr.rowcount
        self.invalidate_model(['productive_status', 'target_hours'])
        return count

    @api.model
    def _cron_finalize_days(self):
        """Grade the In Progress rows once their day is over. A laptop that
        is off after midnight sends nothing, so nothing else would."""
        count = self._xn_refresh_status(only_pending=True)
        if count:
            _logger.info("xn_activity: graded %s finished days", count)

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
            # The usage view, not the raw slots: it carries the effective
            # category (department overrides, Windows / System) and counts
            # idle time of "Count Idle as Active" apps as active, so the
            # footer totals match the day row.
            'res_model': 'xn.activity.app.usage',
            'view_mode': 'tree,pivot,graph',
            'views': [
                (self.env.ref(
                    'xn_activity.view_xn_activity_app_usage_detail_tree').id,
                 'tree'),
                (False, 'pivot'),
                (False, 'graph'),
            ],
            # [id, name]: the web client reads search_view_id[0].
            'search_view_id': [self.env.ref(
                'xn_activity.view_xn_activity_app_usage_search').id, False],
            'domain': [('day_key', '=', self.day_key),
                       ('date', '=', self.date)],
            'context': {'group_by': ['category', 'app_id'], 'create': False},
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
        # Connection checks follow the 5-minute data.
        cr.execute("DELETE FROM xn_activity_net WHERE local_date < %s",
                   (raw_cut,))
        cr.execute("DELETE FROM xn_activity_day WHERE date < %s", (sum_cut,))
        days = cr.rowcount
        cr.execute("DELETE FROM xn_activity_view_log WHERE date < %s",
                   (sum_cut,))
        self.env.invalidate_all()
        _logger.info("xn_activity: purged %s slots before %s, %s days before %s",
                     slots, raw_cut, days, sum_cut)
