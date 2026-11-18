# -*- coding: utf-8 -*-
"""Data for Activity > Dashboard.

Scope comes from the record rules, read as the current user (no sudo for
activity rows): activity viewers (HR, board) get everyone, a reporting
manager gets their team (everyone below them in the org chart), anyone
else just themselves. Panels with names or housekeeping are added only for
the groups allowed to see them:

- "Worth a conversation" (people under target): Board of Directors only.
- "To sort out" (unclassified apps, unlinked sign-ins, notices): HR.
"""
from collections import defaultdict
from datetime import timedelta

from odoo import models, fields, api, _

from .activity_digest import LOW_DAYS
from .activity_settings import get_settings, AGENT_VERSION

LONG_DAY_COUNT = 3       # out-of-hours days in the period
SPLIT_ORDER = ['productive', 'neutral', 'unclassified', 'unproductive',
               'system']


def _avg(total, count):
    return total / count if count else 0.0


class XnActivityDayDashboard(models.Model):
    _inherit = 'xn.activity.day'

    # ------------------------------------------------------------------
    # Periods and scope
    # ------------------------------------------------------------------

    @api.model
    def _xn_dash_period(self, period):
        """(start, end, previous start, previous end, label)."""
        today = fields.Date.context_today(self)
        if period == 'month':
            start = today.replace(day=1)
            end = today
            prev_end = start - timedelta(days=1)
            prev_start = prev_end.replace(day=1)
            prev_end = min(prev_end, prev_start + (end - start))
            label = start.strftime('%B %Y')
        else:
            start = today - timedelta(days=today.weekday())
            if period == 'last':
                start -= timedelta(days=7)
            end = start + timedelta(days=6)
            prev_start = start - timedelta(days=7)
            prev_end = end - timedelta(days=7)
            label = _('Week of %s', start.strftime('%d %b %Y'))
        return start, end, prev_start, prev_end, label

    @api.model
    def _xn_dash_scope(self):
        user = self.env.user
        if user.has_group('xn_activity.group_xn_activity_viewer'):
            return 'all', _('All employees'), None
        team = self.env['hr.employee'].search(
            [('id', 'child_of', user.employee_ids.ids)])
        reports = team - user.employee_ids
        if len(reports) == 1:
            return 'team', _('Your team (1 person)'), team
        if reports:
            return 'team', _('Your team (%s people)', len(reports)), team
        return 'self', _('Just you'), team

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------

    @staticmethod
    def _xn_counted(days):
        """Working days with screen time and no time off: the days the
        averages and the target percentage are measured on."""
        return days.filtered(lambda d: d.screen_hours > 0
                             and d.day_kind == 'working' and not d.time_off)

    def _xn_stats(self):
        counted = self._xn_counted(self)
        n = len(counted)
        return {
            'days': n,
            'screen': _avg(sum(counted.mapped('screen_hours')), n),
            'productive': _avg(sum(counted.mapped('productive_hours')), n),
            'on_target': _avg(len(counted.filtered(
                lambda d: d.productive_status == 'good')) * 100.0, n),
        }

    @staticmethod
    def _xn_low_people(days):
        """{employee: [day rows]} under half the target on LOW_DAYS+
        working days (same test as the weekly digest)."""
        low = defaultdict(list)
        for d in days.filtered(lambda r: r.linked and r.day_kind == 'working'
                               and not r.time_off
                               and r.productive_status in ('low', 'none')):
            low[d.employee_id].append(d)
        return {e: rows for e, rows in low.items() if len(rows) >= LOW_DAYS}

    @api.model
    def xn_dashboard_data(self, period='week', department_id=False):
        start, end, prev_start, prev_end, label = self._xn_dash_period(period)
        scope, scope_label, team = self._xn_dash_scope()
        user = self.env.user
        is_board = user.has_group('xn_activity.group_xn_activity_board')
        is_hr = user.has_group('hr.group_hr_user')

        dept_domain = [('department_id', '=', int(department_id))] \
            if department_id else []
        days = self.search([('date', '>=', start), ('date', '<=', end)]
                           + dept_domain)
        prev = self.search([('date', '>=', prev_start),
                            ('date', '<=', prev_end)] + dept_domain)
        now_stats = days._xn_stats()
        prev_stats = prev._xn_stats()
        low_now = self._xn_low_people(days)
        low_prev = self._xn_low_people(prev)

        today = fields.Date.context_today(self)
        out = {
            'period': period,
            'label': label,
            'start': fields.Date.to_string(start),
            'end': fields.Date.to_string(min(end, today)),
            'scope': scope,
            'scope_label': scope_label,
            'is_board': is_board,
            'is_hr': is_hr,
            'target': get_settings(self.env)['productive_target'],
            'departments': self._xn_dash_departments(),
            'kpis': {
                'now': now_stats, 'prev': prev_stats,
                'low_people': len(low_now), 'low_people_prev': len(low_prev),
            },
            'by_day': self._xn_dash_by_day(days, start, min(end, today)),
            'split': self._xn_dash_split(start, end, dept_domain),
            'departments_table': self._xn_dash_dept_table(days, prev),
            'long_days': self._xn_dash_long_days(days),
            'apps': self._xn_dash_apps(start, end, dept_domain),
            'laptops': self._xn_dash_laptops(scope, team),
            'today': self._xn_dash_today(dept_domain)
            if start <= today <= end else None,
        }
        if is_board:
            out['attention'] = [{
                'employee_id': emp.id,
                'name': emp.name,
                'department': emp.department_id.name or '',
                'days': len(rows),
                'productive': _avg(sum(r.productive_hours for r in rows),
                                   len(rows)),
                'notes': '; '.join('%s: %s' % (r.date.strftime('%a'), r.note)
                                   for r in sorted(rows, key=lambda r: r.date)
                                   if r.note),
            } for emp, rows in sorted(low_now.items(),
                                      key=lambda kv: -len(kv[1]))]
        if is_hr:
            out['to_sort'] = self._xn_dash_to_sort(days, start)
        return out

    def _xn_dash_departments(self):
        groups = self.read_group([('department_id', '!=', False)],
                                 ['department_id'], ['department_id'])
        return sorted(({'id': g['department_id'][0],
                        'name': g['department_id'][1]} for g in groups),
                      key=lambda d: d['name'])

    @api.model
    def _xn_dash_by_day(self, days, start, end):
        out = []
        d = start
        while d <= end:
            rows = days.filtered(lambda r, d=d: r.date == d
                                 and r.screen_hours > 0)
            n = len(rows)
            out.append({
                'date': fields.Date.to_string(d),
                'label': d.strftime('%a %d') if (end - start).days > 7
                else d.strftime('%a'),
                'people': n,
                'screen': _avg(sum(rows.mapped('screen_hours')), n),
                'productive': _avg(sum(rows.mapped('productive_hours')), n),
            })
            d += timedelta(days=1)
        return out

    @api.model
    def _xn_dash_split(self, start, end, dept_domain):
        Usage = self.env['xn.activity.app.usage']
        domain = [('date', '>=', start), ('date', '<=', end)] + dept_domain
        groups = Usage.read_group(domain, ['active_hours:sum',
                                           'idle_hours:sum'], ['category'])
        by_cat = {g['category']: g['active_hours'] or 0.0 for g in groups}
        idle = sum(g['idle_hours'] or 0.0 for g in groups)
        total = sum(by_cat.values()) + idle
        out = [{'key': k, 'hours': by_cat.get(k, 0.0),
                'pct': _avg(by_cat.get(k, 0.0) * 100.0, total)}
               for k in SPLIT_ORDER]
        out.append({'key': 'idle', 'hours': idle,
                    'pct': _avg(idle * 100.0, total)})
        return out

    @api.model
    def _xn_dash_dept_table(self, days, prev):
        def by_dept(rows):
            out = defaultdict(lambda: self.browse())
            for r in rows:
                out[r.department_id] |= r
            return out
        now = by_dept(days.filtered('linked'))
        before = by_dept(prev.filtered('linked'))
        table = []
        for dept, rows in sorted(now.items(),
                                 key=lambda kv: kv[0].name or 'zzz'):
            s = rows._xn_stats()
            p = before.get(dept, self.browse())._xn_stats()
            table.append({
                'id': dept.id or False,
                'name': dept.name or _('(no department)'),
                'people': len(set(rows.mapped('day_key'))),
                'screen': s['screen'],
                'productive': s['productive'],
                'on_target': s['on_target'],
                'delta': (s['on_target'] - p['on_target'])
                if p['days'] else None,
            })
        return table

    @api.model
    def _xn_dash_long_days(self, days):
        """People with LONG_DAY_COUNT+ out-of-hours days (late, early,
        weekend or holiday): a count, no names."""
        counts = defaultdict(int)
        for d in days.filtered(lambda r: r.out_of_hours and r.linked):
            counts[d.employee_id.id] += 1
        return len([1 for c in counts.values() if c >= LONG_DAY_COUNT])

    @api.model
    def _xn_dash_apps(self, start, end, dept_domain):
        Usage = self.env['xn.activity.app.usage']
        groups = Usage.read_group(
            [('date', '>=', start), ('date', '<=', end)] + dept_domain,
            ['active_hours:sum'], ['app_id'],
            orderby='active_hours desc', limit=6)
        apps = self.env['xn.activity.app'].browse(
            [g['app_id'][0] for g in groups if g['app_id']])
        cat = {a.id: ('system' if a.is_system and a.category in
                      ('neutral', 'unclassified') else a.category)
               for a in apps}
        return [{'name': g['app_id'][1], 'hours': g['active_hours'] or 0.0,
                 'category': cat.get(g['app_id'][0], 'unclassified')}
                for g in groups if g['app_id']]

    @api.model
    def _xn_dash_laptops(self, scope, team):
        Device = self.env['xn.activity.device']
        if scope == 'all':
            devices = Device.search([])
        else:
            # Devices are viewer-only; a manager sees their team's laptops
            # (name and state only).
            devices = Device.sudo().search(
                [('employee_id', 'in', team.ids)]) if team else Device
        stale = devices.filtered('stale')
        old = devices.filtered(lambda d: d.agent_version
                               and d.agent_version != AGENT_VERSION)
        issues = [{'name': d.name,
                   'status': _('Silent since %s',
                               fields.Date.to_string(d.last_seen.date()))
                   if d.last_seen else _('Never reported'),
                   'warn': True} for d in stale[:5]]
        issues += [{'name': d.name,
                    'status': _('Clock %s min off',
                                abs(d.clock_offset or 0) // 60),
                    'warn': False}
                   for d in (devices - stale).filtered('clock_flag')[:3]]
        return {
            'reporting': len(devices) - len(stale),
            'total': len(devices),
            'stale': len(stale),
            'old_agent': len(old),
            'issues': issues,
        }

    @api.model
    def _xn_dash_today(self, dept_domain):
        today = fields.Date.context_today(self)
        days = self.search([('date', '=', today)] + dept_domain,
                           order='user_label')
        return self._xn_timelines(days)

    @api.model
    def _xn_dash_to_sort(self, days, start):
        apps = self.env['xn.activity.app'].sudo().search([
            ('category', '=', 'unclassified'),
            ('create_date', '>=', fields.Datetime.to_datetime(start)),
        ], order='create_date desc')
        unlinked = days.filtered(lambda d: not d.linked)
        seen = {}
        for d in unlinked:
            seen.setdefault(d.user_label, d.computers or '')
        tracked = days.filtered('linked').mapped('employee_id').sudo()
        no_notice = tracked.filtered(lambda e: not e.xn_activity_notice_date)
        return {
            'new_apps': apps.mapped('name')[:12],
            'new_apps_count': len(apps),
            'unlinked': [{'key': k, 'computers': v}
                         for k, v in sorted(seen.items())],
            'no_notice': sorted(no_notice.mapped('name')),
        }
