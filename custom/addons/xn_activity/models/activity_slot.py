# -*- coding: utf-8 -*-
from odoo import models, fields, api


def day_key_for(employee_id, user_key):
    """Who a day row belongs to: the employee if linked, else the raw sign-in."""
    return 'emp:%d' % employee_id if employee_id else user_key


class XnActivitySlot(models.Model):
    """Raw 5-minute data: one row per device, sign-in, slot start and app.

    Rows are written only by the ingest endpoint (SQL upsert, see
    controllers/main.py) and deleted by the nightly retention job. The unique
    constraint makes a resent slot overwrite instead of duplicating.
    """
    _name = 'xn.activity.slot'
    _description = 'Activity Slot (5 minutes)'
    _order = 'slot_start desc, app_id'
    _rec_name = 'slot_start'

    # Indexes: this is the busiest table, so it carries only what a query
    # uses. device_id is covered by xn_activity_slot_device_date_idx (and the
    # unique constraint), day_key by xn_activity_slot_day_idx; slot_start is
    # only sorted on within one person's day.
    device_id = fields.Many2one('xn.activity.device', string='Computer',
                                required=True, ondelete='cascade')
    user_key = fields.Char(string='Sign-in', required=True, index=True,
                           help="Microsoft 365 sign-in (UPN), or the Windows "
                                "user name when there is none; lower case.")
    upn = fields.Char(string='UPN')
    login = fields.Char(string='Windows User')
    employee_id = fields.Many2one('hr.employee', ondelete='set null',
                                  index=True)
    day_key = fields.Char(required=True)
    slot_start = fields.Datetime(required=True)
    local_date = fields.Date(required=True, index=True)
    local_minute = fields.Integer(
        help="Minutes since local midnight on the laptop.")
    app_id = fields.Many2one('xn.activity.app', string='App', required=True,
                             ondelete='restrict', index=True)
    app_category = fields.Selection(related='app_id.category',
                                    string='Category')
    active_hours = fields.Float(string='Active', digits=(16, 4))
    idle_hours = fields.Float(string='Idle', digits=(16, 4))
    locked_hours = fields.Float(string='Locked', digits=(16, 4))

    _sql_constraints = [
        ('slot_uniq', 'UNIQUE(device_id, user_key, slot_start, app_id)',
         'Duplicate activity slot.'),
    ]

    def init(self):
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS xn_activity_slot_day_idx
                ON xn_activity_slot (day_key, local_date)
        """)
        # Devices list: count(DISTINCT local_date) per device, index-only.
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS xn_activity_slot_device_date_idx
                ON xn_activity_slot (device_id, local_date)
        """)
