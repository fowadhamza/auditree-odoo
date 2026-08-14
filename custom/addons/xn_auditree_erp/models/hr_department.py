from odoo import models, fields,api


class HrDepartment(models.Model):
    _inherit = "hr.department"

    stage_approval_lines=fields.One2many('stage.approval.user','department_id')

class StageApprovalUser(models.Model):
    _name='stage.approval.user'

    department_id=fields.Many2one('hr.department')
    stage_id=fields.Many2one('hr.recruitment.stage',string="Stage")

    @api.model
    def _getUserGroupId(self):
        return [('groups_id', '=', self.env.ref('xn_auditree_erp.group_job_position_approve').id)]
    approve_user_ids=fields.Many2many('res.users',string="Approvers",domain=_getUserGroupId)







