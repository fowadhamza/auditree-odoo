# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
{
    "name": "Backend Base",

    "author": "Softhealer Technologies",

    "website": "https://www.softhealer.com",

    "support": "support@softhealer.com",

    "version": "0.0.1",

    "license": "OPL-1",

    "category": "Extra Tools",

    "summary": "Material Backend Theme Responsive Backend Theme Backmate Backend Theme Fully Functional Backend Theme Flexible Backend Theme Fast Backend Theme Lightweight Backend Theme Animated Backend Theme Modern Backend Theme Multipurpose Backend Theme Odoo Theme",

    "description": """Backend Base""",

    "depends": ['base_setup',],

    "data": [
        "security/ir.model.access.csv",
        "views/sh_user_push_notification_views.xml",
        "views/res_config_setting.xml",
    ],
    'assets': {
        'web.assets_backend': [

            # pyeval domain
            # "sh_backend_base/static/src/lib/pyeval.js",

            #Notification
            'sh_backend_base/static/src/xml/notification_menu.xml',
            'sh_backend_base/static/src/scss/notification.scss',
            'sh_backend_base/static/src/js/systray_activity_menu.js',
            'sh_backend_base/static/src/scss/light_icon/style.css',
            'sh_backend_base/static/src/scss/regular_icon/style.css',
            'sh_backend_base/static/src/scss/thin_icon/style.css',

            # Push Notification
            'https://www.gstatic.com/firebasejs/8.4.3/firebase-app.js',
            'https://www.gstatic.com/firebasejs/8.4.3/firebase-messaging.js',
            'sh_backend_base/static/src/js/firebase.js',
        ],
    },
    "images": ["static/description/background.png", ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
