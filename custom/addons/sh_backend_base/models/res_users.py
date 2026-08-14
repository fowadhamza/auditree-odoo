# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from odoo import models, api

class res_users(models.Model):
    _inherit = "res.users"

    @api.model
    def systray_get_firebase_notifications(self):
        notifications = self.env['sh.user.push.notification'].sudo().search([('user_id','=',self.env.uid)],limit=25, order='msg_read,id desc')
        unread_notifications = self.env['sh.user.push.notification'].sudo().search([('user_id','=',self.env.uid),('msg_read','=',False)])
        data_notifications = []
        for notification in notifications:
            data_notifications.append({
                'id':notification.id,
                'desc':notification.description,
                'name':notification.name,
                'user_id':notification.user_id,
                'datetime':notification.datetime,
                'uid':notification.user_id.id,
                'res_model':notification.res_model,
                'res_id':notification.res_id,
                'msg_read':notification.msg_read ,
                })

        return list(data_notifications), len(unread_notifications)

    @api.model
    def systray_get_firebase_all_notifications(self):
        notifications = self.env['sh.user.push.notification'].search([('user_id','=',self.env.uid)],order='msg_read,id desc')
        unread_notifications = self.env['sh.user.push.notification'].search([('user_id','=',self.env.uid),('msg_read','=',False)])
        data_notifications = []
        for notification in notifications:
            data_notifications.append({
                'id':notification.id,
                'desc':notification.description,
                'name':notification.name,
                'user_id':notification.user_id,
                'datetime':notification.datetime,
                'uid':notification.user_id.id,
                'res_model':notification.res_model,
                'res_id':notification.res_id,
                'msg_read':notification.msg_read,
                })

        return list(data_notifications), len(unread_notifications)
