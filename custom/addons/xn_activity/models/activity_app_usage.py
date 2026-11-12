# -*- coding: utf-8 -*-
from odoo import models, fields, tools

from .activity_app import CATEGORIES


class XnActivityAppUsage(models.Model):
    """App usage across people and dates, with the effective category
    (department override, else the app's own). SQL view over the slots."""
    _name = 'xn.activity.app.usage'
    _description = 'Activity App Usage'
    _auto = False
    _order = 'date desc'

    date = fields.Date(readonly=True)
    employee_id = fields.Many2one('hr.employee', readonly=True)
    user_key = fields.Char(string='Sign-in', readonly=True)
    department_id = fields.Many2one('hr.department', readonly=True)
    app_id = fields.Many2one('xn.activity.app', string='App', readonly=True)
    category = fields.Selection(CATEGORIES, readonly=True)
    active_hours = fields.Float(string='Active', readonly=True)
    idle_hours = fields.Float(string='Idle', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW xn_activity_app_usage AS (
                SELECT s.id,
                       s.local_date AS date,
                       s.employee_id,
                       s.user_key,
                       e.department_id,
                       s.app_id,
                       COALESCE(r.category, a.category) AS category,
                       s.active_hours,
                       s.idle_hours
                  FROM xn_activity_slot s
                  JOIN xn_activity_app a ON a.id = s.app_id
             LEFT JOIN hr_employee e ON e.id = s.employee_id
             LEFT JOIN xn_activity_app_rule r ON r.app_id = s.app_id
                                             AND r.department_id = e.department_id
            )
        """)
