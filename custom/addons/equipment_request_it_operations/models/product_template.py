# Copyright 2021 Creu Blanca
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_asset = fields.Boolean(
        default=False, string="Is Employee Asset"
    )

    asset_req_count=fields.Integer(string="Asset Request Count",compute="_compute_asset_req")

    def _compute_asset_req(self):
        for rec in self:
            request_lines = self.env['equipment.detail'].sudo().search([('product_id', '=', rec.id), ('equipment_detail_id.status', '=', 'assigned')])
            req_ids = request_lines.mapped('equipment_detail_id')
            rec.asset_req_count=len(req_ids)


    def action_view_asset_requests(self):
        print()
        action = self.env.ref('equipment_request_it_operations.equipment_request_action').read()[0]
        active_id= self.env.context.get('active_id')
        request_lines=self.env['equipment.detail'].sudo().search([('product_id','=',active_id),('equipment_detail_id.status','=','assigned')])
        req_ids=request_lines.mapped('equipment_detail_id')
        action['domain']=[('id','in',req_ids.ids)]
        return action
