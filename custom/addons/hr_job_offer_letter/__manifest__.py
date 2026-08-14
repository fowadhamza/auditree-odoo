{
    'name': 'Job Offer Letter',
    "version": "17.0.0.0",
    "category": "HRMS",
    "summary": "Auditree ERP",
    "description": """Auditree ERP""",
    "license": "OPL-1",
    "author": "shameem",
    'depends': ['hr_recruitment'],
    'data': [
        'data/mail_data.xml',
        'views/he_application_view.xml',
    ],
    'installable': True,
    'application': False,
}
