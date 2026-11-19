# -*- coding: utf-8 -*-
"""Connection quality per laptop, sign-in and 5-minute slot (agent 1.3+).

The agent sends, per slot: connection type (wired / Wi-Fi / mobile / other /
none), the Windows "metered" flag, Wi-Fi signal bars (0-5), TCP connect time
to our server and to Microsoft 365, whether its report went through, and,
at random times, the download speed of a small file from our own bucket.
No network names, IP addresses or locations are sent.

Rows are keyed by (device, sign-in, slot), not by employee, so linking a
sign-in to an employee later needs no update here: the timelines find a
person's rows through the slots of the day (same device and sign-in). There
is no menu or record rule for this model; reports read it with sudo for
days the user may already read, and HR Managers can list it for support.
"""
from odoo import models, fields, api

CONN_TYPES = [
    ('wired', 'Wired'),
    ('wifi', 'Wi-Fi'),
    ('mobile', 'Mobile Data'),
    ('other', 'Other'),
    ('none', 'No Connection'),
]

QUALITIES = [
    ('excellent', 'Excellent'),
    ('good', 'Good'),
    ('fair', 'Fair'),
    ('slow', 'Slow'),
    ('offline', 'Offline'),
    ('unknown', 'Unknown'),
]
QUALITY_LABELS = dict(QUALITIES)
CONN_LABELS = dict(CONN_TYPES)

# Response time (TCP connect, ms) and download speed (Mbps) per grade; the
# worse of the two decides. Grades: 4 excellent, 3 good, 2 fair, 1 slow.
RTT_LIMITS = [(50, 4), (100, 3), (200, 2)]
MBPS_LIMITS = [(25, 4), (10, 3), (3, 2)]
GRADE_NAMES = {4: 'excellent', 3: 'good', 2: 'fair', 1: 'slow'}
QUALITY_ORDER = {'offline': 0, 'slow': 1, 'fair': 2, 'good': 3,
                 'excellent': 4, 'unknown': 5}


def net_quality(conn_type, rtt_ms, m365_ms, mbps, sends_ok, sends_failed):
    """One grade for a slot from what the agent measured."""
    if conn_type == 'none' or (sends_failed and not sends_ok
                               and rtt_ms is None and m365_ms is None):
        return 'offline'
    grades = []
    rtts = [r for r in (rtt_ms, m365_ms) if r is not None]
    if rtts:
        worst = max(rtts)
        grades.append(next((g for limit, g in RTT_LIMITS if worst < limit), 1))
    if mbps is not None:
        grades.append(next((g for limit, g in MBPS_LIMITS if mbps >= limit),
                           1))
    if not grades:
        return 'unknown'
    return GRADE_NAMES[min(grades)]


def net_label(conn_type, metered, bars):
    """'Wired', 'Wi-Fi 4/5', 'Wi-Fi 3/5, metered', 'Mobile Data'."""
    if not conn_type:
        return ''
    label = CONN_LABELS.get(conn_type, conn_type)
    if conn_type == 'wifi' and bars is not None and bars >= 0:
        label += ' %s/5' % bars
    if metered and conn_type != 'none':
        label += ', metered'
    return label


class XnActivityNet(models.Model):
    _name = 'xn.activity.net'
    _description = 'Activity Connection Check (5 minutes)'
    _order = 'slot_start desc'
    _rec_name = 'slot_start'

    device_id = fields.Many2one('xn.activity.device', string='Computer',
                                required=True, ondelete='cascade')
    user_key = fields.Char(string='Sign-in', required=True)
    slot_start = fields.Datetime(required=True)
    local_date = fields.Date(required=True)
    local_minute = fields.Integer()
    conn_type = fields.Selection(CONN_TYPES, string='Connection')
    metered = fields.Boolean()
    signal_bars = fields.Integer(string='Wi-Fi Signal (0-5)')
    rtt_ms = fields.Integer(string='Server (ms)',
                            help="TCP connect time to our server.")
    m365_ms = fields.Integer(string='Microsoft 365 (ms)',
                             help="TCP connect time to Microsoft 365.")
    down_mbps = fields.Float(string='Download (Mbps)', digits=(16, 1))
    sends_ok = fields.Integer(string='Reports Sent')
    sends_failed = fields.Integer(string='Reports Failed')
    quality = fields.Selection(QUALITIES, index=True)

    _sql_constraints = [
        ('net_uniq', 'UNIQUE(device_id, user_key, slot_start)',
         'Duplicate connection check.'),
    ]

    def init(self):
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS xn_activity_net_date_idx
                ON xn_activity_net (local_date, user_key)
        """)

    # ------------------------------------------------------------------
    # Reading, for the timelines and the dashboard
    # ------------------------------------------------------------------

    @api.model
    def _xn_rows_for(self, pairs_by_day):
        """{(day_key, date): {(device_id, user_key), ...}} ->
        {(day_key, date): [row dicts]}. Callers pass only days the user may
        read; the rows themselves are read with sudo (no record rules)."""
        out = {k: [] for k in pairs_by_day}
        if not pairs_by_day:
            return out
        dates = {d for _k, d in pairs_by_day}
        keys = {uk for pairs in pairs_by_day.values() for _dev, uk in pairs}
        if not keys:
            return out
        rows = self.sudo().search_read(
            [('local_date', 'in', list(dates)), ('user_key', 'in', list(keys))],
            ['device_id', 'user_key', 'local_date', 'local_minute',
             'conn_type', 'metered', 'signal_bars', 'rtt_ms', 'm365_ms',
             'down_mbps', 'sends_ok', 'sends_failed', 'quality'])
        by_date = {}
        for (day_key, date), pairs in pairs_by_day.items():
            by_date.setdefault(date, []).append((day_key, pairs))
        for r in rows:
            pair = (r['device_id'][0], r['user_key'])
            for day_key, pairs in by_date.get(r['local_date'], []):
                if pair in pairs:
                    out[(day_key, r['local_date'])].append(r)
        return out

    @staticmethod
    def _xn_strip(rows):
        """5-minute strip for a timeline: [{m, q, title}], the worst grade
        when several laptops reported the same slot."""
        by_minute = {}
        for r in rows:
            m = r['local_minute'] or 0
            cur = by_minute.get(m)
            if cur is None or QUALITY_ORDER[r['quality'] or 'unknown'] < \
                    QUALITY_ORDER[cur['quality'] or 'unknown']:
                by_minute[m] = r
        out = []
        for m, r in sorted(by_minute.items()):
            q = r['quality'] or 'unknown'
            parts = [QUALITY_LABELS[q],
                     net_label(r['conn_type'], r['metered'], r['signal_bars'])]
            if r['rtt_ms']:
                parts.append('server %s ms' % r['rtt_ms'])
            if r['m365_ms']:
                parts.append('Microsoft 365 %s ms' % r['m365_ms'])
            if r['down_mbps']:
                parts.append('%.1f Mbps' % r['down_mbps'])
            out.append({'m': m, 'q': q,
                        'title': ', '.join(p for p in parts if p)})
        return out

    @staticmethod
    def _xn_summary(rows):
        """'Wired 6:10, Wi-Fi 1:20 (metered 0:40). Slow 0:25, offline 0:10.'"""
        if not rows:
            return ''
        def hm(n):
            minutes = n * 5
            return '%d:%02d' % (minutes // 60, minutes % 60)
        by_type, metered, slow, offline = {}, 0, 0, 0
        for r in rows:
            t = r['conn_type'] or 'other'
            by_type[t] = by_type.get(t, 0) + 1
            if r['metered']:
                metered += 1
            if r['quality'] == 'slow':
                slow += 1
            elif r['quality'] == 'offline':
                offline += 1
        order = ['wired', 'wifi', 'mobile', 'other', 'none']
        text = ', '.join('%s %s' % (CONN_LABELS[t], hm(by_type[t]))
                         for t in order if by_type.get(t))
        if metered:
            text += ' (metered %s)' % hm(metered)
        problems = []
        if slow:
            problems.append('slow %s' % hm(slow))
        if offline:
            problems.append('offline %s' % hm(offline))
        if problems:
            text += '. ' + ', '.join(problems).capitalize()
        speeds = [r['down_mbps'] for r in rows if r['down_mbps']]
        if speeds:
            speeds.sort()
            text += '. Median speed %.1f Mbps' % speeds[len(speeds) // 2]
        return text + '.'
