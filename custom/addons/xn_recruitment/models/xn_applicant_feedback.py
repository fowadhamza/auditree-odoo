# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import _, api, fields, models

RECOMMENDATIONS = [
    ('next', 'Shortlist for next round'),
    ('hold', 'Hold'),
    ('reject', 'Reject'),
]


class XnApplicantFeedback(models.Model):
    _name = 'xn.applicant.feedback'
    _description = 'Interview Feedback'
    _order = 'date desc, id desc'
    _rec_name = 'applicant_id'

    applicant_id = fields.Many2one(
        'hr.applicant', string='Candidate', required=True, ondelete='cascade', index=True)
    job_id = fields.Many2one(related='applicant_id.job_id', store=True, string='Job Position')
    department_id = fields.Many2one(
        related='applicant_id.department_id', store=True, string='Department')
    company_id = fields.Many2one(related='applicant_id.company_id', store=True)
    stage_id = fields.Many2one(
        'hr.recruitment.stage', string='Round', required=True,
        help="The round this interview was for.")
    xn_round = fields.Selection(related='stage_id.xn_round', store=True, string='Hiring Step')
    interviewer_id = fields.Many2one(
        'res.users', string='Interviewer', required=True, index=True,
        default=lambda self: self.env.user)
    date = fields.Date(string='Interview Date', required=True, default=fields.Date.context_today)
    recommendation = fields.Selection(RECOMMENDATIONS, required=True)
    comments = fields.Text(required=True)

    @api.model_create_multi
    def create(self, vals_list):
        feedbacks = super().create(vals_list)
        for feedback in feedbacks:
            feedback._xn_after_submit()
        return feedbacks

    def _xn_after_submit(self):
        """Note it on the application, ping the recruiter, close the to-do."""
        self.ensure_one()
        applicant = self.applicant_id.sudo()
        label = dict(RECOMMENDATIONS).get(self.recommendation, '')
        recruiter = applicant.user_id or applicant.job_id.user_id
        applicant.message_post(
            body=Markup(_("<b>%(round)s feedback</b> from %(who)s: <b>%(rec)s</b><br/>%(text)s")) % {
                'round': self.stage_id.name,
                'who': self.interviewer_id.name,
                'rec': label,
                'text': self.comments,
            },
            author_id=self.interviewer_id.partner_id.id,
            partner_ids=recruiter.partner_id.ids if recruiter else [],
            subtype_xmlid='mail.mt_note')
        todo = applicant.activity_ids.filtered(
            lambda activity: activity.user_id == self.interviewer_id)
        if todo:
            todo.action_feedback(feedback=_("Feedback submitted: %s", label))
