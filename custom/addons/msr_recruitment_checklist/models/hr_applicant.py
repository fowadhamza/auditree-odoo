from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    checklist_ids = fields.One2many(comodel_name='recruitment.checklist', string='Check list',
                                    inverse_name='applicant_id', store=True)

    progress = fields.Float("Progress", store=True, group_operator="avg", help="Display progress of application.")

    application_checklist_ids = fields.One2many(comodel_name='application.recruitment.checklist', string='Check list',
                                                inverse_name='applicant_id', )

    # @api.onchange('checklist_ids')
    # def _onchange_checklist(self):
    #     for rec in self:
    #         line_ids = self.env['recruitment.checklist'].search([]).ids
    #         lines = len(rec.mapped('checklist_ids'))
    #         if line_ids:
    #             rec.progress = round((lines / len(line_ids)) * 100)
    #         else:
    #             rec.progress = 0

    @api.onchange('application_checklist_ids')
    def _onchange_is_done(self):
        for rec in self:
            line_ids = self.env['recruitment.checklist'].search([]).ids
            lines = len(rec.application_checklist_ids.filtered(lambda l: l.is_done))
            if line_ids:
                rec.progress = round((lines / len(line_ids)) * 100)
            else:
                rec.progress = 0



    @api.model
    def default_get(self, fields_list):
        res = super(HrApplicant, self).default_get(fields_list)
        checklist_data = self.env['recruitment.checklist'].sudo().search([])
        lines = []
        for data in checklist_data:
            vals = {
                'checklist_id': data.id,
            }
            lines.append((0, 0, vals))
        res.update({'application_checklist_ids': lines})
        return res


class HrApplicantRecruitChecklist(models.Model):
    _name = 'application.recruitment.checklist'

    applicant_id = fields.Many2one('hr.applicant', string="Application")
    checklist_id = fields.Many2one('recruitment.checklist', string="name")
    date = fields.Date(string="Date")
    note = fields.Text(string="Note")
    is_done = fields.Boolean(striung="Done")


