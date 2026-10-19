# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import fields, models

class WebPushNotification(models.Model):
    _name = 'sh.push.notification'
    _description = 'Web Push Notification'

    user_id = fields.Many2one("res.users",string="User")
    user_type=fields.Selection([('public','Public'),('portal','Portal'),('internal','Internal')],string="User Type")
    datetime = fields.Datetime("Registration Time")
    register_id = fields.Char("Registration Id")
