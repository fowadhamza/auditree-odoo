# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api

CLOCK_FLAG_SECONDS = 300
STALE_WORKING_DAYS = 2


def _working_days_back(now, days):
    """The datetime `days` working days (Mon-Fri) before `now`."""
    d = now
    left = days
    while left > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


class XnActivityDevice(models.Model):
    _name = 'xn.activity.device'
    _description = 'Activity Agent Device'
    _order = 'last_seen desc'

    name = fields.Char(string='Computer', required=True, index=True)
    last_user_key = fields.Char(string='Last Sign-in')
    employee_id = fields.Many2one('hr.employee', string='Last Employee',
                                  ondelete='set null')
    first_seen = fields.Datetime()
    last_seen = fields.Datetime(index=True)
    agent_version = fields.Char()
    clock_offset = fields.Integer(
        string='Clock Offset (s)',
        help="Laptop clock minus server clock at the last report. Over 5 "
             "minutes is flagged: slot times from this laptop may be off.")
    clock_flag = fields.Boolean(string='Clock Off', compute='_compute_clock_flag',
                                store=True)
    days_reported = fields.Integer(compute='_compute_days_reported')
    stale = fields.Boolean(
        string='Not Reporting', compute='_compute_stale',
        search='_search_stale',
        help="No report for %d or more working days." % STALE_WORKING_DAYS)
    # Rate limiting, per device, updated in SQL by the ingest endpoint.
    rate_window_start = fields.Datetime(readonly=True)
    rate_count = fields.Integer(readonly=True)

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'This computer already exists.'),
    ]

    @api.depends('clock_offset')
    def _compute_clock_flag(self):
        for dev in self:
            dev.clock_flag = abs(dev.clock_offset or 0) > CLOCK_FLAG_SECONDS

    def _compute_days_reported(self):
        counts = {}
        if self.ids:
            self.env.cr.execute("""
                SELECT device_id, count(DISTINCT local_date)
                  FROM xn_activity_slot
                 WHERE device_id IN %s
              GROUP BY device_id
            """, (tuple(self.ids),))
            counts = dict(self.env.cr.fetchall())
        for dev in self:
            dev.days_reported = counts.get(dev.id, 0)

    def _stale_cutoff(self):
        return _working_days_back(fields.Datetime.now(), STALE_WORKING_DAYS)

    def _compute_stale(self):
        cutoff = self._stale_cutoff()
        for dev in self:
            dev.stale = not dev.last_seen or dev.last_seen < cutoff

    def _search_stale(self, operator, value):
        cutoff = self._stale_cutoff()
        stale = (operator == '=') == bool(value)
        if stale:
            return ['|', ('last_seen', '=', False), ('last_seen', '<', cutoff)]
        return [('last_seen', '>=', cutoff)]
