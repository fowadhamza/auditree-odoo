# Copyright 2021 Creu Blanca
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class Employee(models.Model):
    _inherit = "hr.employee"


    asset_req_count=fields.Integer(string="Asset Request Count",compute="_compute_asset_req")
    asset_line_ids=fields.One2many('equipment.detail','employee_id',string="Assets",)

    def _compute_asset_req(self):
        for rec in self:
            req_ids = self.env['equipment.request'].sudo().search([('employee_name_id', '=', rec.id), ('status', '=', 'assigned')])
            rec.asset_req_count=len(req_ids)


    def action_view_asset_requests(self):
        for rec in self:
            action = self.env.ref('equipment_request_it_operations.equipment_request_action').read()[0]
            req_ids=self.env['equipment.request'].sudo().search([('employee_name_id','=',rec.id),('status','=','assigned')])
            action['domain']=[('id','in',req_ids.ids)]
            return action
