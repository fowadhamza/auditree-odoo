# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import models, fields, api, _

from .activity_settings import get_settings

_logger = logging.getLogger(__name__)

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
    active = fields.Boolean(
        default=True,
        help="Archive a retired laptop so it no longer raises alerts. It "
             "comes back by itself if it reports again.")
    stale_alerted_on = fields.Datetime(
        string='Alert Sent', readonly=True,
        help="When the 'not reporting' alert went out. Cleared when the "
             "laptop reports again, so each silence alerts once.")
    last_user_key = fields.Char(string='Last Sign-in')
    rejected_user_key = fields.Char(
        string='Rejected Sign-in', readonly=True,
        help="Last sign-in from this laptop that Work Accounts Only refused "
             "(a local Windows account, or a work account that matches no "
             "employee). Nothing was stored for it.")
    rejected_at = fields.Datetime(string='Rejected At', readonly=True)
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

    @api.model
    def _xn_alert_recipients(self):
        configured = get_settings(self.env)['alert_to']
        if configured:
            return [e.strip() for e in configured.split(',') if e.strip()]
        return self.env['xn.activity.day']._xn_digest_recipients()

    @api.model
    def _cron_stale_alert(self):
        """Weekday email: laptops that have gone quiet. Once per silence."""
        now = fields.Datetime.now()
        if now.weekday() >= 5:
            return
        devices = self.sudo().search([
            ('stale', '=', True),
            ('stale_alerted_on', '=', False),
            ('last_seen', '!=', False),
        ], order='last_seen')
        if not devices:
            return
        to = self._xn_alert_recipients()
        if not to:
            _logger.info("xn_activity: %d laptops not reporting, no alert "
                         "recipients", len(devices))
            return
        rows = Markup('').join(
            Markup('<tr><td style="padding:4px 8px">%s</td>'
                   '<td style="padding:4px 8px">%s</td>'
                   '<td style="padding:4px 8px">%s</td>'
                   '<td style="padding:4px 8px">%s</td></tr>') % (
                d.name, d.employee_id.name or d.last_user_key or '-',
                fields.Datetime.to_string(d.last_seen), d.agent_version or '-')
            for d in devices)
        body = Markup(
            '<p>These laptops have not reported activity for %d or more '
            'working days. The agent may have been removed or blocked by '
            'antivirus, the laptop may be off or away, or the user may not '
            'have signed in.</p>'
            '<table style="border-collapse:collapse;font-size:13px">'
            '<tr><th style="text-align:left;padding:4px 8px">Computer</th>'
            '<th style="text-align:left;padding:4px 8px">Last user</th>'
            '<th style="text-align:left;padding:4px 8px">Last seen (UTC)</th>'
            '<th style="text-align:left;padding:4px 8px">Agent</th></tr>'
            '%s</table>'
            '<p style="color:#888">You get this once per laptop until it '
            'reports again. Archive a retired laptop in Employees &gt; '
            'Activity &gt; Devices to stop alerts for it.</p>'
        ) % (STALE_WORKING_DAYS, rows)
        self.env['mail.mail'].sudo().create({
            'subject': _('Activity: %d laptop(s) not reporting', len(devices)),
            'email_to': ','.join(to),
            'body_html': body,
            'auto_delete': True,
        })
        devices.write({'stale_alerted_on': now})
        _logger.info("xn_activity: stale alert for %s", ', '.join(devices.mapped('name')))
