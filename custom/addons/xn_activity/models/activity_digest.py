# -*- coding: utf-8 -*-
import logging
from collections import defaultdict
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import models, fields, api, _

from .activity_settings import get_settings

_logger = logging.getLogger(__name__)

LOW_DAYS = 3   # working days under half the target before someone is listed


def _hm(hours):
    minutes = int(round((hours or 0) * 60))
    return '%d:%02d' % (minutes // 60, minutes % 60)


def _table(headers, rows):
    head = Markup('').join(Markup('<th style="text-align:left;padding:4px 8px;'
                                  'border-bottom:1px solid #ccc">%s</th>') % h
                           for h in headers)
    body = Markup('')
    for r in rows:
        body += Markup('<tr>%s</tr>') % Markup('').join(
            Markup('<td style="padding:4px 8px;vertical-align:top">%s</td>')
            % c for c in r)
    return Markup('<table style="border-collapse:collapse;font-size:13px">'
                  '<tr>%s</tr>%s</table>') % (head, body)


class XnActivityDayDigest(models.Model):
    _inherit = 'xn.activity.day'

    @api.model
    def _cron_weekly_digest(self):
        """Monday email to HR covering the previous Monday-Sunday."""
        today = fields.Date.context_today(self)
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        html = self._xn_digest_html(start, end)
        to = self._xn_digest_recipients()
        if not to:
            _logger.info("xn_activity: weekly digest has no recipients")
            return
        self.env['mail.mail'].sudo().create({
            'subject': _('Activity digest: %s to %s', start, end),
            'email_to': ','.join(to),
            'body_html': html,
            'auto_delete': True,
        })

    @api.model
    def _xn_digest_recipients(self):
        configured = get_settings(self.env)['digest_to']
        if configured:
            return [e.strip() for e in configured.split(',') if e.strip()]
        group = self.env.ref('hr.group_hr_manager')
        users = group.users.filtered(lambda u: u.active and u.email
                                     and not u.share)
        return sorted(set(users.mapped('email')))

    @api.model
    def _xn_digest_html(self, start, end):
        Day = self.sudo()
        target = get_settings(self.env)['productive_target']
        days = Day.search([('date', '>=', start), ('date', '<=', end)])

        # Totals per department
        dept = defaultdict(lambda: [set(), 0.0, 0.0, 0.0])
        for d in days:
            t = dept[d.department_id.name or _('(no department)')]
            t[0].add(d.day_key)
            t[1] += d.screen_hours
            t[2] += d.productive_hours
            t[3] += d.idle_hours
        dept_rows = [(name, len(v[0]), _hm(v[1]), _hm(v[2]), _hm(v[3]))
                     for name, v in sorted(dept.items())]

        # People under half the target on several working days
        low = defaultdict(list)
        for d in days.filtered(lambda r: r.linked and r.day_kind == 'working'
                               and not r.time_off
                               and r.productive_status in ('low', 'none')):
            low[d.employee_id].append(d)
        low_rows = []
        for emp, rows in sorted(low.items(), key=lambda kv: kv[0].name or ''):
            if len(rows) < LOW_DAYS:
                continue
            notes = '; '.join('%s: %s' % (r.date.strftime('%a'), r.note)
                              for r in rows if r.note)
            low_rows.append((emp.name, len(rows),
                             _hm(sum(r.productive_hours for r in rows)),
                             notes or '-'))

        # Laptops not reporting, unlinked sign-ins, new unclassified apps
        stale = self.env['xn.activity.device'].sudo().search(
            [('stale', '=', True)])
        stale_rows = [(dv.name, dv.last_user_key or '-',
                       fields.Datetime.to_string(dv.last_seen) if dv.last_seen
                       else '-') for dv in stale]
        unlinked = sorted(set(days.filtered(lambda r: not r.linked)
                              .mapped('user_label')))
        new_apps = self.env['xn.activity.app'].sudo().search([
            ('category', '=', 'unclassified'),
            ('create_date', '>=', fields.Datetime.to_datetime(start)),
        ])

        parts = [Markup('<p>Activity from %s to %s. Daily productive target: '
                        '%s.</p>') % (start, end, _hm(target))]
        parts.append(Markup('<h3>By department</h3>'))
        parts.append(_table(['Department', 'People', 'Screen', 'Productive',
                             'Idle'], dept_rows) if dept_rows
                     else Markup('<p>No activity.</p>'))
        parts.append(Markup('<h3>Under half the target on %d or more working '
                            'days</h3>') % LOW_DAYS)
        parts.append(_table(['Employee', 'Days', 'Productive', 'Day notes'],
                            low_rows) if low_rows else Markup('<p>None.</p>'))
        parts.append(Markup('<h3>Laptops not reporting</h3>'))
        parts.append(_table(['Computer', 'Last sign-in', 'Last seen (UTC)'],
                            stale_rows) if stale_rows
                     else Markup('<p>None.</p>'))
        if unlinked:
            parts.append(Markup('<h3>Sign-ins not linked to an employee</h3>'
                                '<p>%s</p>') % ', '.join(unlinked))
        if new_apps:
            parts.append(Markup('<h3>New unclassified apps</h3><p>%s</p>')
                         % ', '.join(new_apps.mapped('name')))
        parts.append(Markup('<p style="color:#888">Times are hours:minutes. '
                            'Open Employees &gt; Activity for detail.</p>'))
        return Markup('').join(escape(p) if not isinstance(p, Markup) else p
                               for p in parts)
