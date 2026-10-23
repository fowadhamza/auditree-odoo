# -*- coding: utf-8 -*-
from odoo import fields, models


class XnApplicantStageLog(models.Model):
    """One row per stage move. Feeds the daily "progressed to" report.

    Written by hr.applicant.create/write; nothing else should create rows.
    """
    _name = 'xn.applicant.stage.log'
    _description = 'Applicant Stage Movement'
    _order = 'date desc, id desc'
    _rec_name = 'applicant_id'

    applicant_id = fields.Many2one(
        'hr.applicant', string='Candidate', required=True, ondelete='cascade', index=True)
    job_id = fields.Many2one(related='applicant_id.job_id', store=True, string='Job Position')
    department_id = fields.Many2one(
        related='applicant_id.department_id', store=True, string='Department')
    company_id = fields.Many2one(related='applicant_id.company_id', store=True)
    from_stage_id = fields.Many2one('hr.recruitment.stage', string='From')
    to_stage_id = fields.Many2one('hr.recruitment.stage', string='To', required=True)
    to_round = fields.Selection(related='to_stage_id.xn_round', store=True, string='Moved To Step')
    date = fields.Datetime(string='Moved At', required=True, default=fields.Datetime.now)
    log_date = fields.Date(
        string='Date', required=True, index=True, default=fields.Date.context_today)
    user_id = fields.Many2one('res.users', string='Moved By', default=lambda self: self.env.user)
