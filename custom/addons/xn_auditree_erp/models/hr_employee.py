from odoo import models, fields, api, _
from datetime import date, datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class HREmployee(models.Model):
    _inherit = "hr.employee"

    sql_constraints = [
        ('adhar_pan_uniq', 'unique (adhar_no, pan_no)', 'PAN ,Adhar must be unique per company.'),
    ]

    adhar_no = fields.Char(string="Adhar No")
    pan_no = fields.Char(string="PAN No")
    personal_mobile = fields.Char(string="Private Mobile", readonly=False)
    homeland_phone = fields.Char(string="Homeland Phone")
    joining_date = fields.Date(compute='_compute_joining_date',
                               string='Joining Date', store=True, readonly=False,
                               help="Employee joining date computed from the"
                                    " contract start date")

    employee_type = fields.Selection(selection_add=[('temporary', 'Temporary'), ], ondelete={'temporary': 'cascade'})
    emp_blood_type = fields.Selection(
        [('a+', 'A+'), ('a-', 'A-'), ('b+', 'B+'), ('b-', 'B-'), ('o+', 'O+'), ('o-', 'O-'), ('ab+', 'AB+'),
         ('ab-', 'AB-')], string="Blood Group")

    probation_notified = fields.Boolean(
        string="Probation Notification Sent",
        default=False,
        help="Set to True once a probation reminder email has been sent, "
             "preventing duplicate emails on subsequent cron runs.",
    )

    def action_check_employee_type(self):
        employees = self.env['hr.employee'].sudo().search([])
        for emp in employees:
            if emp.joining_date and emp.employee_type == 'temporary':
                cutoff = datetime.now().date() - timedelta(days=90)
                if cutoff > emp.joining_date:
                    emp.update({'employee_type': 'employee'})

    notice_perioid = fields.Integer(string="Notice Period", related='contract_id.notice_days')
    probation_period = fields.Integer(string="Probation Period", default=90)
    probation_notification_type = fields.Selection([
        ('after_2_half_month', 'Notification after 2.5 months'),
        ('before_months', 'Notification before end of 3 months'),
        ('after_3months', 'On Completion of 3 months'),

    ], string='Probation End Notification Type',
        help="Select type of the documents expiry notification.")

    def mail_probation_reminder(self):
        """Cron: send probation-end notification emails.

        A `probation_notified` flag prevents duplicate emails from being
        sent on subsequent cron runs after the trigger date has been reached.
        """
        _logger.info("mail_probation_reminder: starting cron run")
        today = datetime.now().date()

        # Map notification type -> threshold days
        thresholds = {
            'after_2_half_month': 75,
            'before_months': 80,
            'after_3months': 90,
        }

        employees = self.env['hr.employee'].sudo().search([
            ('active', '=', True),
            ('probation_notification_type', '!=', False),
            ('probation_notified', '=', False),   # skip already-notified
            ('joining_date', '!=', False),
        ])

        for record in employees:
            days = thresholds.get(record.probation_notification_type)
            if not days:
                continue

            cutoff = today - timedelta(days=days)
            if cutoff <= record.joining_date:
                # Not yet reached the threshold date
                continue

            employee_name = record.name
            mail_content = (
                f"Hello {employee_name},<br>"
                f"You have completed Probation Period of {days} days."
            )
            subject = _('Probation Period-Notification')
            mail_values = {
                'subject': subject,
                'author_id': self.env.user.partner_id.id,
                'body_html': mail_content,
                'email_to': record.work_email,
            }
            self.env['mail.mail'].create(mail_values).send()
            # Mark as notified so we don't send again next cron run
            record.sudo().write({'probation_notified': True})
            _logger.info(
                "mail_probation_reminder: sent notification to %s (employee %s)",
                record.work_email, record.id,
            )

        _logger.info("mail_probation_reminder: done")


class HrJob(models.Model):
    _inherit = "hr.job"

    def approve_job_position(self):
        self.is_published = True
