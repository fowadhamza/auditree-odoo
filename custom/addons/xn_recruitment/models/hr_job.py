# -*- coding: utf-8 -*-
from odoo import fields, models

SALARY_GROUP = 'hr_recruitment.group_hr_recruitment_user'


class HrJob(models.Model):
    _inherit = 'hr.job'

    # Requisition: what HR needs before sourcing starts. Number of people is
    # core no_of_recruitment, designation is the job name, roles and
    # responsibilities are the core Job Summary.
    xn_requested_by_id = fields.Many2one(
        'res.users', string='Requested By', default=lambda self: self.env.user,
        help="Operations Manager who raised the requirement.")
    xn_request_reason = fields.Selection(
        [('client', 'Client requirement'),
         ('management', 'Management (growth, new service line, capacity gap)')],
        string='Requirement From')
    xn_opened_on = fields.Date(
        string='Opened On', default=fields.Date.context_today,
        help="Start of the hiring clock for this position (days open / days to close).")
    xn_deadline = fields.Date(string='Hiring Deadline')
    xn_ctc_min = fields.Float(string='CTC Band From (annual, INR)', groups=SALARY_GROUP)
    xn_ctc_max = fields.Float(string='CTC Band To (annual, INR)', groups=SALARY_GROUP)
    xn_experience = fields.Char(string='Experience Level', help="e.g. 2-4 years after qualification")
    xn_qualification = fields.Char(string='Qualification', help="e.g. CA Inter, ACCA, B.Com")
    xn_joining_requirement = fields.Char(
        string='Joining Requirement', help="e.g. Immediate, or within 30 days")
    xn_panel_id = fields.Many2one(
        'xn.recruitment.panel', string='Interview Panel',
        help="Who interviews in each round. A candidate moved into a round is "
             "emailed to that round's interviewers with the CV and the previous "
             "round's feedback.")
