# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    "name": "Auditree ERP",
    "version": "18.0.1.0.0",
    "category": "HRMS",
    "summary": "Auditree ERP",
    "description": """Auditree ERP""",
    "license": "OPL-1",
    "author": "shameem",
    "website": "https://www.xetensolutions.com",
    "depends": ["base",
                "hr","website_hr_recruitment",
                "project",
                "hr_attendance",
                "xn_user_custom","account","msr_bank_customization","msr_company_header",
                ],
    "data": [
        "data/mail_data.xml",
        'security/secutity.xml',
        "security/ir.model.access.csv",
        "views/hr_department_views.xml",
        'views/hr_employee_views.xml',
        'views/hr_job_views.xml',
        'views/hr_recruitment_view.xml',
        'views/project_view.xml',
        'views/hr_attendance_view.xml',
        'report/report.xml',
        'report/invoice_report_template.xml',
        'report/report_payslip.xml',
        #'views/res_users_view.xml',
        ],

    "auto_install": False,
    "application": True,
    "installable": True,
    'live_test_url':'https://youtu.be/hFgGdnCcB6Q',
    "images":['static/description/Most-Buying-Product.gif'],
}


