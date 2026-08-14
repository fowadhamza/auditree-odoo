from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta

class RecruitmentChecklist(models.Model):
    _name = 'recruitment.checklist'

    name=fields.Char(string="Reference",  required=True,default=lambda self: _("New"),tracking=True,)
    applicant_id=fields.Many2one('hr.applicant',string="Application")
