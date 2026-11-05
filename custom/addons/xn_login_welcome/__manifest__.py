# -*- coding: utf-8 -*-
{
    "name": "Auditree Login Welcome",
    "summary": "A short animated welcome, shown once after each login.",
    "description": """
After a user signs in, the backend shows a full-screen greeting for about two
seconds: the company logo inside a ring that draws itself, "Good morning,
<first name>" and today's date. Clicking skips it. Reloads and new tabs in the
same login do not show it again, and users who ask their system for reduced
motion never see it.

Uninstalling the module removes it completely.
""",
    "version": "17.0.1.0.0",
    "category": "Hidden",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": ["web"],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "xn_login_welcome/static/src/welcome/*",
        ],
    },
    "installable": True,
    "application": False,
}
