# -*- coding: utf-8 -*-
from odoo import models, fields


class XnActivityViewLog(models.Model):
    """Who opened another person's 5-minute detail, and when."""
    _name = 'xn.activity.view.log'
    _description = 'Activity Detail View Log'
    _order = 'create_date desc'

    viewer_id = fields.Many2one('res.users', string='Viewed By', readonly=True,
                                required=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', string='Person Viewed',
                                  readonly=True, ondelete='set null')
    user_label = fields.Char(string='Sign-in', readonly=True)
    date = fields.Date(string='Day Viewed', readonly=True)
    create_date = fields.Datetime(string='Viewed On', readonly=True)
