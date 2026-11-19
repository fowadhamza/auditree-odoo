# -*- coding: utf-8 -*-
"""Timeline data for the day form widget and the Team Timeline screen.

One entry per 5-minute slot that has data, in laptop-local minutes, with a
single state for colouring. Read through xn.activity.app.usage as the
current user, so the record rules decide whose slots come back (employees:
their own; activity viewers: everyone) -- no sudo here.

Connection quality (agent 1.3+) comes from xn.activity.net for the
(computer, sign-in) pairs found in those same usage rows, so it never
reaches further than the activity the user may already read.
"""
from collections import defaultdict

from odoo import models, fields, api, _

# Order matters: the client draws the legend in this order.
TIMELINE_STATES = [
    ('productive', 'Productive'),
    ('neutral', 'Neutral'),
    ('unclassified', 'Unclassified'),
    ('unproductive', 'Unproductive'),
    ('system', 'Windows / System'),
    ('idle', 'Idle'),
    ('locked', 'Locked'),
]


def _mmss(seconds):
    seconds = int(round(seconds))
    return '%d:%02d' % (seconds // 60, seconds % 60)


def _slot_state(apps):
    """apps: {label: [active s, idle s, locked s, category]} -> (state,
    label of the app that decides it)."""
    act = sum(v[0] for v in apps.values())
    idle = sum(v[1] for v in apps.values())
    locked = sum(v[2] for v in apps.values())
    if locked and locked >= act + idle:
        top = max(apps, key=lambda k: apps[k][2])
        return 'locked', top
    if idle > act:
        top = max(apps, key=lambda k: apps[k][1])
        return 'idle', top
    top = max(apps, key=lambda k: apps[k][0])
    return apps[top][3] or 'unclassified', top


class XnActivityDayTimeline(models.Model):
    _inherit = 'xn.activity.day'

    @api.model
    def _xn_timelines(self, days):
        """[{day fields..., 'slots': [...]}] for a recordset of days."""
        if not days:
            return []
        Usage = self.env['xn.activity.app.usage']
        rows = Usage.search_read(
            [('day_key', 'in', list(set(days.mapped('day_key')))),
             ('date', 'in', list(set(days.mapped('date'))))],
            ['day_key', 'date', 'local_minute', 'app_id', 'category',
             'active_hours', 'idle_hours', 'locked_hours', 'device_id',
             'user_key'])
        # (day_key, date) -> minute -> app label -> [act, idle, locked, cat]
        grid = defaultdict(lambda: defaultdict(dict))
        # (day_key, date) -> {(device id, sign-in)}: whose connection rows
        # belong to the day.
        sources = defaultdict(set)
        for r in rows:
            if r['device_id']:
                sources[(r['day_key'], r['date'])].add(
                    (r['device_id'][0], r['user_key']))
            label = r['app_id'][1] if r['app_id'] else _('Unknown')
            cell = grid[(r['day_key'], r['date'])][r['local_minute'] or 0]
            v = cell.setdefault(label, [0.0, 0.0, 0.0, r['category']])
            v[0] += r['active_hours'] * 3600
            v[1] += r['idle_hours'] * 3600
            v[2] += r['locked_hours'] * 3600
        Net = self.env['xn.activity.net']
        net_rows = Net._xn_rows_for(dict(sources))
        out = []
        for day in days:
            day_net = net_rows.get((day.day_key, day.date), [])
            slots = []
            for minute, apps in sorted(grid[(day.day_key, day.date)].items()):
                state, top = _slot_state(apps)
                ranked = sorted(apps.items(),
                                key=lambda kv: -(kv[1][0] + kv[1][1]
                                                 + kv[1][2]))
                slots.append({
                    'm': minute,
                    's': state,
                    'app': top,
                    'a': int(round(sum(v[0] for v in apps.values()))),
                    'i': int(round(sum(v[1] for v in apps.values()))),
                    'l': int(round(sum(v[2] for v in apps.values()))),
                    'apps': ', '.join(
                        '%s %s' % (name, _mmss(v[0] + v[1] + v[2]))
                        for name, v in ranked[:3]),
                })
            out.append({
                'id': day.id,
                'label': day.user_label,
                'date': fields.Date.to_string(day.date),
                'department': day.department_id.name or '',
                'department_id': day.department_id.id or False,
                'screen_hours': day.screen_hours,
                'productive_hours': day.productive_hours,
                'idle_hours': day.idle_hours,
                'status': day.productive_status,
                'time_off': day.time_off or '',
                'note': day.note or '',
                'slots': slots,
                'net': Net._xn_strip(day_net),
                'net_summary': Net._xn_summary(day_net),
            })
        return out

    @api.model
    def xn_timeline_data(self, day_ids):
        """Timelines for these days, limited to what the user may read."""
        days = self.search([('id', 'in', list(day_ids or []))])
        return {
            'states': TIMELINE_STATES,
            'days': self._xn_timelines(days),
        }

    @api.model
    def xn_team_timeline(self, date):
        """Every day row the user may read for one date, by name."""
        date = fields.Date.to_date(date) or fields.Date.context_today(self)
        days = self.search([('date', '=', date)], order='user_label')
        timelines = self._xn_timelines(days)
        departments = sorted(
            {(t['department_id'], t['department']) for t in timelines
             if t['department_id']}, key=lambda d: d[1])
        return {
            'date': fields.Date.to_string(date),
            'states': TIMELINE_STATES,
            'departments': [{'id': d[0], 'name': d[1]} for d in departments],
            'days': timelines,
        }
