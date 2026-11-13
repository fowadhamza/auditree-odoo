# -*- coding: utf-8 -*-
{
    "name": "Auditree Activity Tracking",
    "summary": "Daily Work Metrics from a small Windows agent: active, idle "
               "and locked time per employee per day, productive time by "
               "program.",
    "description": """
A PowerShell agent on each Windows laptop reports, every 5 minutes, how long
the signed-in user was active, idle or locked, per foreground program. Odoo
stores the 5-minute slots and a daily summary per person.

* Employees are linked by their Microsoft 365 sign-in (UPN = work email), or
  by a Windows user name set on the employee.
* Programs are classified Productive / Neutral / Unproductive, with
  per-department overrides.
* HR sees everyone; each employee sees only their own days and can add a day
  note (client visit, offline work).
* Partners/directors (checkbox) and shared mailboxes are never stored.
* Agent Setup (HR Manager) builds the install.ps1 that Endpoint Central
  deploys.

No titles, URLs, keystrokes or screenshots are collected. See README.md.
    """,
    "version": "17.0.1.2.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_holidays",
        "mail",
        "resource",
    ],
    "data": [
        "security/xn_activity_groups.xml",
        "security/ir.model.access.csv",
        "security/xn_activity_security.xml",
        "data/xn_activity_app_data.xml",
        "data/ir_cron_data.xml",
        "views/activity_day_views.xml",
        "views/activity_slot_views.xml",
        "views/activity_app_views.xml",
        "views/activity_device_views.xml",
        "views/activity_note_views.xml",
        "views/activity_setup_views.xml",
        "views/hr_employee_views.xml",
        "views/xn_activity_menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
