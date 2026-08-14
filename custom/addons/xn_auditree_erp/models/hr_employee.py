from odoo import models, fields, api, _
from datetime import date
from dateutil import parser
from datetime import datetime, timedelta


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

    def action_check_employee_type(self):
        employees = self.env['hr.employee'].sudo().search([])
        for emp in employees:
            if emp.joining_date and emp.employee_type == 'temporary':
                past = datetime.now() - timedelta(days=90)
                joining_date = emp.joining_date
                if past > parser.parse(str(joining_date)):
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
        print("mail_probation_reminder")
        for record in self.env['hr.employee'].sudo().search([('active','=',True)]):

            if record.probation_notification_type == 'after_2_half_month':
                if record.joining_date:
                    past = datetime.now() - timedelta(days=75)
                    joining_date = record.joining_date
                    if past > parser.parse(str(joining_date)):
                        employee_name = record.name

                        probation_date_str = str(record.probation_period)
                        mail_content = (
                            f"Hello {employee_name},<br>You have completed Probation Period of 75 days"""
                        )
                        subject = _('Probation Period-Notification')
                        main_content = {
                            'subject': subject,
                            'author_id': self.env.user.partner_id.id,
                            'body_html': mail_content,
                            'email_to': record.work_email,
                        }
                        self.env['mail.mail'].create(main_content).send()
            if record.probation_notification_type == 'after_3months':
                if record.joining_date:
                    past = datetime.now() - timedelta(days=90)
                    joining_date = record.joining_date
                    print("past",past,joining_date)
                    if past > parser.parse(str(joining_date)):
                        employee_name = record.name
                        mail_content = (
                            f"Hello {employee_name},<br>You have completed Probation Period of 90 days"""
                        )
                        subject = _('Probation Period-Notification')
                        main_content = {
                            'subject': subject,
                            'author_id': self.env.user.partner_id.id,
                            'body_html': mail_content,
                            'email_to': record.work_email,
                        }
                        self.env['mail.mail'].create(main_content).send()
            if record.probation_notification_type == 'before_months':
                            if record.joining_date:
                                past = datetime.now() - timedelta(days=80)
                                joining_date = record.joining_date
                                if past > parser.parse(str(joining_date)):
                                    employee_name = record.name
                                    mail_content = (
                                        f"Hello {employee_name},<br>You have completed Probation Period of 80 days"""
                                    )
                                    subject = _('Probation Period-Notification')
                                    main_content = {
                                        'subject': subject,
                                        'author_id': self.env.user.partner_id.id,
                                        'body_html': mail_content,
                                        'email_to': record.work_email,
                                    }
                                    self.env['mail.mail'].create(main_content).send(force_send=True)


class HrJob(models.Model):
    _inherit = "hr.job"

    def approve_job_position(self):
        self.is_published = True
