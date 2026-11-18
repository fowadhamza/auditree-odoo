# -*- coding: utf-8 -*-
from odoo import models, fields, tools

from .activity_app import CATEGORIES

# The usage view adds one bucket of its own: Windows itself (lock screen,
# Start menu, ...) when it is not classified Productive or Unproductive.
USAGE_CATEGORIES = CATEGORIES + [('system', 'Windows / System')]


class XnActivityAppUsage(models.Model):
    """App usage per 5-minute slot, with the effective category (department
    override, else the app's own) and idle time of "Count Idle as Active"
    apps moved to active, as the daily totals count it. SQL view over the
    slots.

    Used by App Usage (pivot/graph) and by the 5-Minute Detail of a day, so
    the detail groups by category and its totals match the day row.
    """
    _name = 'xn.activity.app.usage'
    _description = 'Activity App Usage'
    _auto = False
    _order = 'date desc'

    date = fields.Date(readonly=True)
    slot_start = fields.Datetime(readonly=True)
    day_key = fields.Char(readonly=True)
    employee_id = fields.Many2one('hr.employee', readonly=True)
    user_key = fields.Char(string='Sign-in', readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    device_id = fields.Many2one('xn.activity.device', string='Computer',
                                readonly=True)
    app_id = fields.Many2one('xn.activity.app', string='App', readonly=True)
    category = fields.Selection(USAGE_CATEGORIES, readonly=True)
    active_hours = fields.Float(string='Active', readonly=True)
    idle_hours = fields.Float(string='Idle', readonly=True)
    locked_hours = fields.Float(string='Locked', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW xn_activity_app_usage AS (
                SELECT s.id,
                       s.local_date AS date,
                       s.slot_start,
                       s.day_key,
                       s.employee_id,
                       s.user_key,
                       e.department_id,
                       s.device_id,
                       s.app_id,
                       CASE WHEN a.is_system
                                 AND COALESCE(r.category, a.category)
                                     IN ('neutral', 'unclassified')
                            THEN 'system'
                            ELSE COALESCE(r.category, a.category)
                       END AS category,
                       s.active_hours + CASE WHEN a.idle_as_active
                                             THEN s.idle_hours ELSE 0 END
                           AS active_hours,
                       CASE WHEN a.idle_as_active THEN 0
                            ELSE s.idle_hours END AS idle_hours,
                       s.locked_hours
                  FROM xn_activity_slot s
                  JOIN xn_activity_app a ON a.id = s.app_id
             LEFT JOIN hr_employee e ON e.id = s.employee_id
             LEFT JOIN xn_activity_app_rule r ON r.app_id = s.app_id
                                             AND r.department_id = e.department_id
            )
        """)
