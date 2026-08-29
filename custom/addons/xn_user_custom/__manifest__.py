# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.
{
    "name": "Auditree USER Custom ERP",
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
                ],
    "data": [

        'views/res_users_view.xml',
        ],

    "auto_install": False,
    "application": True,
    "installable": True,
    'live_test_url':'https://youtu.be/hFgGdnCcB6Q',
    "images":['static/description/Most-Buying-Product.gif'],
}


