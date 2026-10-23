# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.osv import expression
from odoo.tools import formataddr

from .hr_recruitment_stage import INTERVIEW_ROUNDS, ROUND_LABELS
from .xn_applicant_feedback import RECOMMENDATIONS

_logger = logging.getLogger(__name__)

SALARY_GROUP = 'hr_recruitment.group_hr_recruitment_user'
# A refused candidate may reapply after this many months; earlier, HR is told.
REAPPLY_MONTHS = 6
# Interviewers are asked for feedback within a day of being handed a candidate.
FEEDBACK_DUE_DAYS = 1


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    # Core fields, relabelled to how Auditree records them (annual CTC, INR).
    salary_expected = fields.Float(string='Expected CTC (annual, INR)')
    salary_proposed = fields.Float(string='Offered CTC (annual, INR)')
    availability = fields.Date(string='Earliest Joining Date')

    # Candidate details (HR collects these over the phone).
    xn_notice_days = fields.Integer(
        string='Notice Period (days)', tracking=True,
        help="Days still to serve at the current employer; 0 means immediate.")
    xn_qualification = fields.Char(string='Qualification', help="e.g. CA Inter, ACCA, B.Com")
    xn_papers_passed = fields.Char(string='CA / ACCA Papers Passed')
    xn_ca_final_attempts = fields.Integer(string='CA Final Attempts')
    xn_articleship_done = fields.Boolean(string='Articleship Completed')
    xn_total_experience = fields.Float(string='Total Experience (years)', digits=(4, 1))
    xn_relevant_experience = fields.Float(string='Relevant Experience (years)', digits=(4, 1))
    xn_current_ctc = fields.Float(
        string='Current CTC (annual, INR)', tracking=True, group_operator='avg',
        groups=SALARY_GROUP)
    xn_location = fields.Char(string='Location')

    # Where the candidate came from. The channel itself is core source_id.
    xn_agency_id = fields.Many2one(
        'res.partner', string='Recruitment Agency', tracking=True,
        domain=[('xn_is_recruitment_agency', '=', True)])
    xn_referrer_id = fields.Many2one('hr.employee', string='Referred By', tracking=True)
    xn_agency_fee = fields.Float(
        string='Agency Fee (INR)', compute='_compute_xn_agency_fee', store=True,
        groups=SALARY_GROUP,
        help="From the agency's fee rule and the offered CTC, once the candidate has joined.")

    # Progress through the process.
    xn_round = fields.Selection(related='stage_id.xn_round', store=True, string='Hiring Step')
    xn_max_round_order = fields.Integer(
        string='Furthest Step', default=0, readonly=True, copy=False, index=True,
        help="Furthest hiring step ever reached; the hiring reports count from it, "
             "so refused candidates still count as having reached their last round.")
    xn_on_hold = fields.Boolean(string='On Hold', tracking=True, copy=False)
    xn_hold_reason = fields.Selection(
        [('comparing', 'Comparing with other candidates'),
         ('position', 'Position on hold')],
        string='Hold Reason', tracking=True, copy=False)
    xn_feedback_ids = fields.One2many(
        'xn.applicant.feedback', 'applicant_id', string='Interview Feedback')
    xn_feedback_count = fields.Integer(compute='_compute_xn_feedback_count')
    xn_refused_on = fields.Date(string='Refused On', readonly=True, copy=False)
    xn_previous_application_id = fields.Many2one(
        'hr.applicant', string='Previously Refused Application', readonly=True, copy=False)
    xn_reapplied_early = fields.Boolean(
        string='Reapplied Within 6 Months', readonly=True, copy=False)

    # Offer and joining.
    xn_bond_required = fields.Boolean(string='Bond Required', default=True)
    xn_bond_months = fields.Integer(string='Bond Period (months)', default=12)
    xn_no_show = fields.Boolean(string='Did Not Join', tracking=True, copy=False)
    xn_no_show_reason = fields.Char(string='Reason for Not Joining', copy=False)

    @api.depends('salary_proposed', 'date_closed', 'xn_agency_id.xn_agency_fee_type')
    def _compute_xn_agency_fee(self):
        for applicant in self:
            fee = 0.0
            fee_type = applicant.xn_agency_id.xn_agency_fee_type
            if applicant.date_closed and applicant.salary_proposed:
                if fee_type == 'one_month':
                    fee = applicant.salary_proposed / 12.0
                elif fee_type == 'percent':
                    fee = applicant.salary_proposed * 0.0833
            applicant.xn_agency_fee = fee

    @api.depends('xn_feedback_ids')
    def _compute_xn_feedback_count(self):
        for applicant in self:
            applicant.xn_feedback_count = len(applicant.xn_feedback_ids)

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        applicants = super().create(vals_list)
        for applicant in applicants:
            if applicant.stage_id:
                applicant._xn_log_stage(False, applicant.stage_id)
                if applicant.stage_id.xn_round_order:
                    applicant.sudo().xn_max_round_order = applicant.stage_id.xn_round_order
        if not self.env.context.get('xn_skip_reapply_check'):
            applicants._xn_check_reapplication()
        return applicants

    def write(self, vals):
        if vals.get('refuse_reason_id'):
            vals = dict(vals, xn_refused_on=fields.Date.context_today(self))
        if 'stage_id' not in vals:
            return super().write(vals)
        old_stages = {applicant.id: applicant.stage_id for applicant in self}
        res = super().write(vals)
        for applicant in self:
            old_stage = old_stages.get(applicant.id)
            if old_stage != applicant.stage_id:
                applicant._xn_on_stage_changed(old_stage, applicant.stage_id)
        return res

    # ------------------------------------------------------------------
    # Stage changes
    # ------------------------------------------------------------------
    def _xn_on_stage_changed(self, old_stage, new_stage):
        self.ensure_one()
        self._xn_log_stage(old_stage, new_stage)
        if new_stage.xn_round_order > self.xn_max_round_order:
            self.sudo().write({'xn_max_round_order': new_stage.xn_round_order})
        moved_forward = (not old_stage) or (
            new_stage.xn_round_order > old_stage.xn_round_order
            if old_stage.xn_round_order and new_stage.xn_round_order
            else new_stage.sequence > old_stage.sequence)
        if self.active and moved_forward and new_stage.xn_round in INTERVIEW_ROUNDS:
            self._xn_handover_to_interviewers(old_stage, new_stage)

    def _xn_log_stage(self, old_stage, new_stage):
        self.env['xn.applicant.stage.log'].sudo().create({
            'applicant_id': self.id,
            'from_stage_id': old_stage.id if old_stage else False,
            'to_stage_id': new_stage.id,
            'user_id': self.env.uid,
        })

    def _xn_handover_to_interviewers(self, old_stage, new_stage):
        """Give the candidate to the new round's interviewers.

        They become interviewers on the applicant (which is what grants an
        Interviewer-only user access to it), get an email from HR with the CV
        attached and the feedback from the round just finished, and a to-do
        to send their own feedback within a day.
        """
        self.ensure_one()
        round_label = ROUND_LABELS.get(new_stage.xn_round, new_stage.name)
        panel = self.job_id.xn_panel_id
        users = panel._xn_interviewers(new_stage.xn_round) if panel else self.env['res.users']
        if not users:
            reason = (_("job position %s has no interview panel") % (self.job_id.name or '-')
                      if not panel else
                      _("panel %(panel)s has nobody for %(round)s",
                        panel=panel.name, round=round_label))
            self.message_post(
                body=_("Nobody was emailed for %(round)s: %(reason)s.",
                       round=round_label, reason=reason),
                subtype_xmlid='mail.mt_note')
            return

        self.sudo().write({'interviewer_ids': [(4, user.id) for user in users]})

        previous_feedback = self.env['xn.applicant.feedback']
        if old_stage:
            previous_feedback = self.sudo().xn_feedback_ids.filtered(
                lambda feedback: feedback.stage_id == old_stage)
        cvs = self._xn_cv_attachments()
        body = self.env['ir.qweb']._render('xn_recruitment.mail_body_next_interviewer', {
            'applicant': self.sudo(),
            'round_label': round_label,
            'previous_stage': old_stage,
            'feedback': previous_feedback,
            'recommendations': dict(RECOMMENDATIONS),
            'cv_count': len(cvs),
            'url': '%s/web#id=%s&model=hr.applicant&view_type=form' % (
                self.get_base_url(), self.id),
        })
        hr_email = self._xn_hr_email()
        self.env['mail.mail'].sudo().create({
            'subject': _("Interview %(round)s: %(candidate)s for %(job)s",
                         round=round_label,
                         candidate=self.partner_name or self.name,
                         job=self.job_id.name or '-'),
            'email_from': formataddr((_('Auditree HR'), hr_email)),
            'reply_to': hr_email,
            'recipient_ids': [(6, 0, users.partner_id.ids)],
            'body_html': body,
            'attachment_ids': [(6, 0, cvs.ids)],
            'auto_delete': True,
        })
        self.message_post(
            body=Markup(_("Sent to %(people)s for <b>%(round)s</b> with %(count)s CV file(s) "
                          "and %(feedback)s feedback note(s) from the previous round.")) % {
                'people': ', '.join(users.mapped('name')),
                'round': round_label,
                'count': len(cvs),
                'feedback': len(previous_feedback),
            },
            subtype_xmlid='mail.mt_note')
        deadline = fields.Date.context_today(self) + timedelta(days=FEEDBACK_DUE_DAYS)
        for user in users:
            self.sudo().activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=deadline,
                summary=_("Interview and feedback: %s", round_label),
                note=_("Interview the candidate, then use Give Feedback on the application."),
                user_id=user.id)

    def _xn_cv_attachments(self):
        """Files attached to the application, minus images (email signatures)."""
        self.ensure_one()
        attachments = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'hr.applicant'), ('res_id', '=', self.id)])
        return attachments.filtered(
            lambda attachment: not (attachment.mimetype or '').startswith('image/'))

    @api.model
    def _xn_hr_email(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            'xn_recruitment.hr_email', 'hr@auditree.com')

    # ------------------------------------------------------------------
    # Reapplication check
    # ------------------------------------------------------------------
    def _xn_check_reapplication(self):
        """Flag candidates who were refused before, matched on email or phone.

        Within REAPPLY_MONTHS of the refusal HR gets a to-do; after it, only a
        note on the application.
        """
        Applicant = self.sudo().with_context(active_test=False)
        cutoff = fields.Date.context_today(self) - relativedelta(months=REAPPLY_MONTHS)
        for applicant in self:
            keys = []
            if applicant.email_normalized:
                keys.append([('email_normalized', '=', applicant.email_normalized)])
            if applicant.partner_phone_sanitized:
                keys.append([('partner_phone_sanitized', '=', applicant.partner_phone_sanitized)])
            if not keys:
                continue
            domain = expression.AND([
                expression.OR(keys),
                [('id', '!=', applicant.id), ('active', '=', False),
                 ('refuse_reason_id', '!=', False)],
            ])
            matches = Applicant.search(domain)
            if not matches:
                continue
            # Older refusals predate xn_refused_on; their last write is the refusal.
            refused_dates = {app.id: app.xn_refused_on or app.write_date.date() for app in matches}
            previous = max(matches, key=lambda app: refused_dates[app.id])
            refused_on = refused_dates[previous.id]
            early = refused_on > cutoff
            applicant.sudo().write({
                'xn_previous_application_id': previous.id,
                'xn_reapplied_early': early,
            })
            message = _("Previously refused on %(date)s for %(job)s (%(reason)s).",
                        date=refused_on, job=previous.job_id.name or '-',
                        reason=previous.refuse_reason_id.name)
            applicant.message_post(body=message, subtype_xmlid='mail.mt_note')
            responsible = applicant.user_id or applicant.job_id.user_id
            if early and responsible:
                applicant.sudo().activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary=_("Refused candidate reapplied within %s months", REAPPLY_MONTHS),
                    note=message,
                    user_id=responsible.id)

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_xn_give_feedback(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Interview Feedback'),
            'res_model': 'xn.applicant.feedback',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_applicant_id': self.id,
                'default_stage_id': self.stage_id.id,
            },
        }

    def action_xn_open_feedback(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Interview Feedback'),
            'res_model': 'xn.applicant.feedback',
            'view_mode': 'tree,form',
            'domain': [('applicant_id', '=', self.id)],
            'context': {
                'default_applicant_id': self.id,
                'default_stage_id': self.stage_id.id,
            },
        }
