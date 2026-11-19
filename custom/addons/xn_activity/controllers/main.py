# -*- coding: utf-8 -*-
"""Agent endpoints.

POST /xn_activity/ingest  -- laptops, API key in X-Activity-Key
GET  /xn_activity/installer -- HR Manager or Agent Installer, downloads install.ps1
"""
import hmac
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from odoo import http, fields, _
from odoo.exceptions import UserError
from odoo.http import request

from ..models.activity_settings import get_settings
from ..models.activity_setup import build_installer, can_download_installer
from ..models.activity_slot import day_key_for

_logger = logging.getLogger(__name__)

MAX_BODY = 1024 * 1024
MAX_SLOTS = 2000
SLOT_SECONDS = 300
MAX_AGE = timedelta(days=60)
MAX_AHEAD = timedelta(hours=1)
RATE_WINDOW = timedelta(hours=1)
RATE_LIMIT = 60
CLOCK_OFFSET_CAP = 10 * 365 * 86400

_NAME_RE = re.compile(r'[^A-Za-z0-9._@\\-]')


def _json(status, payload):
    return request.make_response(
        json.dumps(payload), status=status,
        headers=[('Content-Type', 'application/json'),
                 ('Cache-Control', 'no-store')])


def _clean(value, limit=128):
    return _NAME_RE.sub('', str(value or '')).strip()[:limit]


def _parse_ts(value):
    """ISO timestamp with offset -> aware datetime, or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.endswith('Z'):
        value = value[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or value != value or value in (float('inf'), float('-inf')):
        raise ValueError('seconds must be a number')
    return min(max(int(value), 0), SLOT_SECONDS)


def _slot(s, now):
    """One slot from the agent -> stored values; None to skip it (no time,
    or outside the accepted window); ValueError when malformed."""
    if not isinstance(s, dict):
        raise ValueError('slot must be an object')
    start = _parse_ts(s.get('start'))
    if start is None:
        raise ValueError('slot start needs a UTC offset')
    start = start.replace(second=0, microsecond=0,
                          minute=start.minute - start.minute % 5)
    active = _seconds(s.get('active', 0))
    idle = _seconds(s.get('idle', 0))
    locked = _seconds(s.get('locked', 0))
    total = active + idle + locked
    if not total:
        return None
    if total > SLOT_SECONDS:
        # Scale down rather than reject: a sampling edge case.
        k = SLOT_SECONDS / float(total)
        active, idle, locked = (int(active * k), int(idle * k),
                                int(locked * k))
    utc = start.astimezone(timezone.utc)
    if utc < now - MAX_AGE or utc > now + MAX_AHEAD:
        return None
    return {
        'start_utc': utc.replace(tzinfo=None),
        'local_date': start.date(),
        'local_minute': start.hour * 60 + start.minute,
        'app': str(s.get('app') or 'unknown')[:128],
        'active': active, 'idle': idle, 'locked': locked,
    }


class XnActivityController(http.Controller):

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _key_ok(self, env, given):
        if not given:
            return False
        params = env['ir.config_parameter'].sudo()
        current = params.get_param('xn_activity.api_key') or ''
        if current and hmac.compare_digest(given.encode(), current.encode()):
            return True
        old = params.get_param('xn_activity.api_key_old') or ''
        until = params.get_param('xn_activity.api_key_old_until')
        if old and until and fields.Datetime.now() < \
                fields.Datetime.to_datetime(until):
            return hmac.compare_digest(given.encode(), old.encode())
        return False

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    @http.route('/xn_activity/ingest', type='http', auth='public',
                methods=['POST'], csrf=False, save_session=False)
    def ingest(self, **kw):
        req = request.httprequest
        env = request.env(su=True)
        if not self._key_ok(env, req.headers.get('X-Activity-Key', '')):
            return _json(403, {'ok': False, 'error': 'forbidden'})
        length = req.content_length or 0
        if length > MAX_BODY:
            return _json(413, {'ok': False, 'error': 'too large'})
        # Odoo re-runs this handler after a serialization failure (two
        # requests creating the same day row or app, see _xn_insert_rows).
        # The stream can only be read once; cache=True keeps the body on the
        # request object, which the retry reuses.
        raw = req.get_data(cache=True)
        if len(raw) > MAX_BODY:
            return _json(413, {'ok': False, 'error': 'too large'})
        try:
            body = json.loads(raw.decode('utf-8-sig'))
            parsed = self._validate(body)
        except (ValueError, TypeError, KeyError, AttributeError,
                OverflowError) as e:
            return _json(400, {'ok': False, 'error': 'malformed: %s' % e})

        device = self._touch_device(env, parsed)
        if device is None:
            return _json(429, {'ok': False, 'error': 'rate limited'})
        stored = self._store(env, device, parsed)
        if parsed['bad_slots']:
            _logger.info("xn_activity: %s skipped %d malformed slots",
                         parsed['device'], parsed['bad_slots'])
        settings = get_settings(env)
        return _json(200, {
            'ok': True,
            'stored': stored,
            'skipped': parsed['bad_slots'],
            'idle_seconds': int(settings['idle_minutes']) * 60,
        })

    def _validate(self, body):
        if not isinstance(body, dict):
            raise ValueError('body must be an object')
        upn = _clean(body.get('upn')).lower()
        if '@' not in upn:
            upn = ''
        login = _clean(body.get('login'), 64).lower()
        if '\\' in login:
            login = login.split('\\')[-1]
        device = _clean(body.get('device'), 64).upper()
        if not device or not (upn or login):
            raise ValueError('device and upn or login are required')
        slots = body.get('slots') or []
        if not isinstance(slots, list):
            raise ValueError('slots must be a list')
        if len(slots) > MAX_SLOTS:
            raise ValueError('more than %d slots' % MAX_SLOTS)
        now = datetime.now(timezone.utc)
        out = []
        bad = 0
        for s in slots:
            # One malformed slot must not reject the batch: the agent keeps
            # a rejected batch and resends it, so the whole queue would be
            # stuck behind it. Skip it and say so in the response.
            try:
                v = _slot(s, now)
            except (ValueError, TypeError, OverflowError):
                bad += 1
                continue
            if v:
                out.append(v)
        sent_at = _parse_ts(body.get('sent_at'))
        offset = int((sent_at - now).total_seconds()) if sent_at else 0
        # Fits the int4 column; anything this far off is flagged anyway.
        offset = max(min(offset, CLOCK_OFFSET_CAP), -CLOCK_OFFSET_CAP)
        return {
            'bad_slots': bad,
            'upn': upn, 'login': login, 'device': device,
            'user_key': upn or login,
            'agent': _clean(body.get('agent'), 16),
            'clock_offset': offset,
            'slots': out,
        }

    def _touch_device(self, env, p):
        """Create/update the device row; None when over the rate limit."""
        cr = env.cr
        now = fields.Datetime.now()
        cr.execute("""
            INSERT INTO xn_activity_device
                   (name, first_seen, last_seen, rate_window_start, rate_count,
                    create_uid, create_date, write_uid, write_date)
            VALUES (%(n)s, %(now)s, %(now)s, %(now)s, 0, 1, %(now)s, 1, %(now)s)
            ON CONFLICT (name) DO NOTHING
        """, {'n': p['device'], 'now': now})
        cr.execute("""
            UPDATE xn_activity_device SET
                   rate_window_start = CASE WHEN rate_window_start IS NULL
                        OR rate_window_start < %(win)s THEN %(now)s
                        ELSE rate_window_start END,
                   rate_count = CASE WHEN rate_window_start IS NULL
                        OR rate_window_start < %(win)s THEN 1
                        ELSE rate_count + 1 END
             WHERE name = %(n)s
         RETURNING id, rate_count
        """, {'n': p['device'], 'now': now, 'win': now - RATE_WINDOW})
        dev_id, count = cr.fetchone()
        if count > RATE_LIMIT:
            return None
        return dev_id

    def _match_employee(self, env, p):
        """(employee id or None, stop?) for this sign-in.

        stop = True means the person is excluded (partner/director, shared
        mailbox) or archived: store nothing.
        """
        cr = env.cr
        emp_id = None
        if p['upn']:
            cr.execute("""
                SELECT id FROM hr_employee
                 WHERE lower(trim(work_email)) = %s
              ORDER BY active DESC, id LIMIT 1
            """, (p['upn'],))
            row = cr.fetchone()
            emp_id = row and row[0]
        if not emp_id and p['login']:
            cr.execute("""
                SELECT id FROM hr_employee
                 WHERE lower(trim(xn_activity_login)) IN %s
              ORDER BY active DESC, id LIMIT 1
            """, (tuple({p['login'], p['user_key']}),))
            row = cr.fetchone()
            emp_id = row and row[0]
        if not emp_id:
            return None, False
        emp = env['hr.employee'].with_context(active_test=False).browse(emp_id)
        if emp._xn_activity_is_excluded() or not emp.active:
            return emp_id, True
        return emp_id, False

    def _store(self, env, device_id, p):
        emp_id, stop = self._match_employee(env, p)
        cr = env.cr
        cr.execute("""
            UPDATE xn_activity_device
               SET last_seen = %s, agent_version = %s, clock_offset = %s,
                   clock_flag = abs(%s) > 300, last_user_key = %s,
                   active = true, stale_alerted_on = NULL,
                   employee_id = %s, write_date = %s
             WHERE id = %s
        """, (fields.Datetime.now(), p['agent'] or None, p['clock_offset'],
              p['clock_offset'], None if stop else p['user_key'],
              None if stop else emp_id, fields.Datetime.now(), device_id))
        env['xn.activity.device'].invalidate_model()
        if stop or not p['slots']:
            return 0
        apps = env['xn.activity.app']._xn_get_or_create(
            {s['app'] for s in p['slots']})
        day_key = day_key_for(emp_id, p['user_key'])
        now = fields.Datetime.now()
        rows = []
        pairs = set()
        for s in p['slots']:
            rows.append((
                device_id, p['user_key'], p['upn'] or None,
                p['login'] or None, emp_id, day_key,
                s['start_utc'], s['local_date'], s['local_minute'],
                apps[s['app']],
                s['active'] / 3600.0, s['idle'] / 3600.0,
                s['locked'] / 3600.0, now, now,
            ))
            pairs.add((day_key, s['local_date']))
        env.flush_all()
        values = ','.join(cr.mogrify(
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,1,%s)", r
        ).decode() for r in rows)
        cr.execute("""
            INSERT INTO xn_activity_slot
                   (device_id, user_key, upn, login, employee_id, day_key,
                    slot_start, local_date, local_minute, app_id,
                    active_hours, idle_hours, locked_hours,
                    create_uid, create_date, write_uid, write_date)
            VALUES """ + values + """
            ON CONFLICT (device_id, user_key, slot_start, app_id) DO UPDATE SET
                   active_hours = EXCLUDED.active_hours,
                   idle_hours = EXCLUDED.idle_hours,
                   locked_hours = EXCLUDED.locked_hours,
                   employee_id = EXCLUDED.employee_id,
                   day_key = EXCLUDED.day_key,
                   write_date = EXCLUDED.write_date
        """)
        env['xn.activity.slot'].invalidate_model()
        env['xn.activity.day']._xn_recompute(pairs)
        return len(rows)

    # ------------------------------------------------------------------
    # Installer download
    # ------------------------------------------------------------------

    @http.route('/xn_activity/installer', type='http', auth='user',
                methods=['GET'])
    def installer(self, **kw):
        if not can_download_installer(request.env.user):
            return request.not_found()
        try:
            content = build_installer(request.env)
        except UserError as e:
            return request.make_response(
                str(e), status=400,
                headers=[('Content-Type', 'text/plain; charset=utf-8')])
        _logger.info("xn_activity: installer downloaded by %s",
                     request.env.user.login)
        return request.make_response(content, headers=[
            ('Content-Type', 'application/octet-stream'),
            ('Content-Disposition', 'attachment; filename="install.ps1"'),
            ('Cache-Control', 'no-store'),
        ])
