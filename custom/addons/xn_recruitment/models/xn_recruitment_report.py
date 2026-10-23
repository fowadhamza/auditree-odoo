# -*- coding: utf-8 -*-
import logging
from datetime import timedelta

from odoo import _, api, fields, models, tools
from odoo.tools import formataddr

from .hr_recruitment_stage import INTERVIEW_ROUNDS, ROUND_LABELS, ROUND_ORDER

_logger = logging.getLogger(__name__)

# Dates in the daily report are Indian dates, whatever the server clock says.
REPORT_TZ = 'Asia/Kolkata'


def _reached(step):
    """SQL: the applicant got at least as far as `step`."""
    return "a.xn_max_round_order >= %d" % ROUND_ORDER[step]


class XnRecruitmentPositionReport(models.Model):
    """Hiring status per job position: the funnel management asks about."""
    _name = 'xn.recruitment.position.report'
    _description = 'Hiring Status by Position'
    _auto = False
    _order = 'department_id, job_id'
    _rec_name = 'job_id'

    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    user_id = fields.Many2one('res.users', string='Recruiter', readonly=True)
    to_hire = fields.Integer(string='Still to Hire', readonly=True)
    opened_on = fields.Date(readonly=True)
    deadline = fields.Date(readonly=True)
    days_open = fields.Integer(string='Days Open', readonly=True)
    days_to_close = fields.Integer(
        string='Days to Close', readonly=True,
        help="Opened-on to the last joining date, once nobody is left to hire.")
    cv_count = fields.Integer(string='CVs Received', readonly=True)
    shortlisted_count = fields.Integer(string='Shortlisted', readonly=True)
    round1_count = fields.Integer(string='Round 1', readonly=True)
    round2_count = fields.Integer(string='Round 2', readonly=True)
    final_count = fields.Integer(string='Final Round', readonly=True)
    decision_count = fields.Integer(string='Decision', readonly=True)
    offer_count = fields.Integer(string='Offers', readonly=True)
    joined_count = fields.Integer(string='Joined', readonly=True)
    pipeline_count = fields.Integer(string='In Pipeline', readonly=True)
    hold_count = fields.Integer(string='On Hold', readonly=True)
    refused_count = fields.Integer(string='Refused', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    j.id AS id,
                    j.id AS job_id,
                    j.department_id AS department_id,
                    j.company_id AS company_id,
                    j.user_id AS user_id,
                    j.no_of_recruitment AS to_hire,
                    COALESCE(j.xn_opened_on, j.create_date::date) AS opened_on,
                    j.xn_deadline AS deadline,
                    (CURRENT_DATE - COALESCE(j.xn_opened_on, j.create_date::date)) AS days_open,
                    CASE WHEN j.no_of_recruitment = 0
                              AND COUNT(a.id) FILTER (WHERE %(joined)s) > 0
                         THEN MAX(a.date_closed)::date - COALESCE(j.xn_opened_on, j.create_date::date)
                    END AS days_to_close,
                    COUNT(a.id) AS cv_count,
                    COUNT(a.id) FILTER (WHERE %(cold_call)s) AS shortlisted_count,
                    COUNT(a.id) FILTER (WHERE %(round1)s) AS round1_count,
                    COUNT(a.id) FILTER (WHERE %(round2)s) AS round2_count,
                    COUNT(a.id) FILTER (WHERE %(final)s) AS final_count,
                    COUNT(a.id) FILTER (WHERE %(decision)s) AS decision_count,
                    COUNT(a.id) FILTER (WHERE %(offer)s) AS offer_count,
                    COUNT(a.id) FILTER (WHERE %(joined)s) AS joined_count,
                    COUNT(a.id) FILTER (WHERE a.active AND NOT (%(joined)s)) AS pipeline_count,
                    COUNT(a.id) FILTER (WHERE a.active AND a.xn_on_hold) AS hold_count,
                    COUNT(a.id) FILTER (WHERE NOT a.active AND a.refuse_reason_id IS NOT NULL)
                        AS refused_count
                FROM hr_job j
                LEFT JOIN hr_applicant a ON a.job_id = j.id
                WHERE j.active
                GROUP BY j.id
            )
        """ % {
            'table': self._table,
            'cold_call': _reached('cold_call'),
            'round1': _reached('round1'),
            'round2': _reached('round2'),
            'final': _reached('final'),
            'decision': _reached('decision'),
            'offer': _reached('offer'),
            'joined': _reached('joined'),
        })

    # ------------------------------------------------------------------
    # Daily email
    # ------------------------------------------------------------------
    @api.model
    def _xn_cron_daily_report(self):
        """Email yesterday's hiring activity and today's status per position.

        Mirrors the update HR posts in Teams: interviews held yesterday and
        candidates progressed yesterday, per position and round, plus the
        open-position funnel. Recipients: system parameter
        xn_recruitment.daily_report_emails (comma separated).
        """
        recipients = self.env['ir.config_parameter'].sudo().get_param(
            'xn_recruitment.daily_report_emails', '')
        recipients = ','.join(email.strip() for email in recipients.split(',') if email.strip())
        if not recipients:
            _logger.info("xn_recruitment: no daily_report_emails set, daily report skipped")
            return
        today = fields.Date.context_today(self.with_context(tz=REPORT_TZ))
        yesterday = today - timedelta(days=1)
        values = self._xn_daily_report_values(yesterday)
        if not (values['positions'] or values['interviews'] or values['progressed']):
            return
        body = self.env['ir.qweb']._render('xn_recruitment.mail_body_daily_report', values)
        hr_email = self.env['hr.applicant']._xn_hr_email()
        self.env['mail.mail'].sudo().create({
            'subject': _("Hiring status - %s", today.strftime('%d %b %Y')),
            'email_from': formataddr((_('Auditree HR'), hr_email)),
            'email_to': recipients,
            'body_html': body,
            'auto_delete': True,
        })

    @api.model
    def _xn_daily_report_values(self, day):
        rounds = [(key, ROUND_LABELS[key]) for key in INTERVIEW_ROUNDS]
        positions = self.sudo().search(['|', ('to_hire', '>', 0), ('pipeline_count', '>', 0)])

        def by_job(records, round_field):
            table = {}
            for record in records:
                key = record.job_id.display_name or _('No position')
                row = table.setdefault(key, {round_key: 0 for round_key, _label in rounds})
                if record[round_field] in row:
                    row[record[round_field]] += 1
            return sorted(table.items())

        feedback = self.env['xn.applicant.feedback'].sudo().search([('date', '=', day)])
        moves = self.env['xn.applicant.stage.log'].sudo().search([
            ('log_date', '=', day), ('to_round', 'in', list(INTERVIEW_ROUNDS))])
        return {
            'day': day,
            'rounds': rounds,
            'positions': positions,
            'interviews': by_job(feedback, 'xn_round'),
            'progressed': by_job(moves, 'to_round'),
        }


class XnRecruitmentSourceReport(models.Model):
    """Which channels and agencies produce hires, not just CVs."""
    _name = 'xn.recruitment.source.report'
    _description = 'Recruitment Source Performance'
    _auto = False
    _order = 'joined_count desc, cv_count desc'

    source_id = fields.Many2one('utm.source', string='Source', readonly=True)
    agency_id = fields.Many2one('res.partner', string='Agency', readonly=True)
    job_id = fields.Many2one('hr.job', string='Job Position', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    cv_count = fields.Integer(string='CVs', readonly=True)
    shortlisted_count = fields.Integer(string='Shortlisted', readonly=True)
    interviewed_count = fields.Integer(string='Interviewed', readonly=True)
    offer_count = fields.Integer(string='Offers', readonly=True)
    joined_count = fields.Integer(string='Joined', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %(table)s AS (
                SELECT
                    MIN(a.id) AS id,
                    a.source_id AS source_id,
                    a.xn_agency_id AS agency_id,
                    a.job_id AS job_id,
                    j.department_id AS department_id,
                    a.company_id AS company_id,
                    COUNT(a.id) AS cv_count,
                    COUNT(a.id) FILTER (WHERE %(cold_call)s) AS shortlisted_count,
                    COUNT(a.id) FILTER (WHERE %(round1)s) AS interviewed_count,
                    COUNT(a.id) FILTER (WHERE %(offer)s) AS offer_count,
                    COUNT(a.id) FILTER (WHERE %(joined)s) AS joined_count
                FROM hr_applicant a
                LEFT JOIN hr_job j ON j.id = a.job_id
                GROUP BY a.source_id, a.xn_agency_id, a.job_id, j.department_id, a.company_id
            )
        """ % {
            'table': self._table,
            'cold_call': _reached('cold_call'),
            'round1': _reached('round1'),
            'offer': _reached('offer'),
            'joined': _reached('joined'),
        })
