# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    xn_activity_login = fields.Char(
        string='Windows User Name', groups='hr.group_hr_user', copy=False,
        help="Only needed when the laptop does not sign in with the work "
             "email (Microsoft 365). Case does not matter.")
    xn_activity_excluded = fields.Boolean(
        string='Exclude from Activity Tracking', groups='hr.group_hr_user',
        copy=False,
        help="Partners and directors. Nothing is stored for them, and "
             "ticking this deletes what was already stored.")
    xn_activity_notice_date = fields.Date(
        string='Monitoring Notice Acknowledged', groups='hr.group_hr_user',
        copy=False)

    @api.constrains('xn_activity_login')
    def _check_xn_activity_login(self):
        for emp in self.filtered('xn_activity_login'):
            login = emp.xn_activity_login.strip().lower()
            self.env.cr.execute("""
                SELECT id FROM hr_employee
                 WHERE lower(trim(xn_activity_login)) = %s AND id != %s
                 LIMIT 1
            """, (login, emp.id))
            if self.env.cr.fetchone():
                raise ValidationError(_(
                    "Windows user name %s is already set on another "
                    "employee.", emp.xn_activity_login))

    def _xn_activity_is_excluded(self):
        """Never tracked: nothing is stored, and what was stored is deleted.
        (Archived employees are not stored either, but their history stays;
        see the ingest endpoint.)"""
        self.ensure_one()
        return self.xn_activity_excluded or self.employee_type == 'system'

    def write(self, vals):
        res = super().write(vals)
        relink = {'xn_activity_login', 'work_email'} & set(vals)
        if vals.get('xn_activity_excluded') or 'employee_type' in vals:
            self._xn_activity_purge_excluded()
        if relink:
            self._xn_activity_relink()
        return res

    def _xn_activity_keys(self):
        """Sign-in keys that belong to these employees."""
        keys = set()
        for emp in self.sudo():
            if emp.work_email:
                keys.add(emp.work_email.strip().lower())
            if emp.xn_activity_login:
                keys.add(emp.xn_activity_login.strip().lower())
        return keys

    def _xn_activity_relink(self):
        """Attribute activity already received under these employees' sign-in
        names to them, and re-point any rows that no longer match."""
        Day = self.env['xn.activity.day']
        cr = self.env.cr
        self.env.flush_all()
        pairs = set()
        for emp in self.sudo().with_context(active_test=False):
            keys = list(emp._xn_activity_keys())
            if emp._xn_activity_is_excluded():
                continue
            # Rows now pointing at this employee but under a key that is no
            # longer theirs: unlink them first.
            cr.execute("""
                UPDATE xn_activity_slot
                   SET employee_id = NULL, day_key = user_key
                 WHERE employee_id = %s AND NOT (user_key = ANY(%s))
             RETURNING user_key, local_date
            """, (emp.id, keys))
            for key, d in cr.fetchall():
                pairs.add((key, d))
                pairs.add(('emp:%d' % emp.id, d))
            if keys:
                # The day rows these slots belong to now (raw key, or a
                # previous employee) must be rebuilt too.
                cr.execute("""
                    SELECT DISTINCT day_key, local_date FROM xn_activity_slot
                     WHERE user_key = ANY(%s)
                """, (keys,))
                pairs.update(cr.fetchall())
                cr.execute("""
                    UPDATE xn_activity_slot s
                       SET employee_id = %s, day_key = %s
                     WHERE user_key = ANY(%s)
                       AND (employee_id IS NULL OR employee_id != %s)
                 RETURNING user_key, local_date
                """, (emp.id, 'emp:%d' % emp.id, keys, emp.id))
                for key, d in cr.fetchall():
                    pairs.add((key, d))
                    pairs.add(('emp:%d' % emp.id, d))
        if pairs:
            self.env['xn.activity.slot'].invalidate_model()
            # Old raw-key rows and rows under a previous employee go away.
            cr.execute("""
                SELECT DISTINCT day_key, date FROM xn_activity_day
                 WHERE day_key = ANY(%s)
            """, ([p[0] for p in pairs],))
            pairs.update(cr.fetchall())
            Day._xn_recompute(pairs)

    def _xn_activity_purge_excluded(self):
        """Delete everything stored for employees who are now excluded."""
        cr = self.env.cr
        self.env.flush_all()
        for emp in self.sudo().with_context(active_test=False):
            if not emp._xn_activity_is_excluded():
                continue
            keys = list(emp._xn_activity_keys())
            cr.execute("""
                DELETE FROM xn_activity_slot
                 WHERE employee_id = %s OR user_key = ANY(%s)
            """, (emp.id, keys))
            cr.execute("""
                DELETE FROM xn_activity_day
                 WHERE employee_id = %s OR day_key = ANY(%s)
            """, (emp.id, keys))
            if cr.rowcount:
                _logger.info("xn_activity: deleted stored activity for "
                             "excluded employee %s", emp.id)
        self.env['xn.activity.slot'].invalidate_model()
        self.env['xn.activity.day'].invalidate_model()
