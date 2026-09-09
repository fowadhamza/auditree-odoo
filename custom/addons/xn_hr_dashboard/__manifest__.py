# -*- coding: utf-8 -*-
{
    "name": "Auditree HR Dashboard",
    "summary": "A self-contained HR dashboard: personal panel, team dates, "
               "and organisation figures for HR managers.",
    "description": """
A standalone HR dashboard client action.

Deliberately depends on nothing but core HR
--------------------------------------------
It reads hr, hr_holidays, hr_attendance, hr_recruitment and hr_timesheet, all
of which any HR deployment already has. It does *not* depend on the Open HRMS
dashboard (hrms_dashboard), on the Events app, or on hr_reward_warning.

That matters because hrms_dashboard drags in ten modules and imports pandas at
load time. On the production server a numpy 2 / pandas 1.5 ABI mismatch made
that import fail outright, which would have taken this dashboard down with it
for no benefit: none of the vendor's UI is rendered here, and only two of its
Python methods were ever used. Both are reimplemented, and the leave trend now
groups months in SQL rather than in a DataFrame.

Panels
------
* A person strip: photo, job, department, payslips, timesheets, contracts,
  Bradford factor, and check in / check out.
* Your team: birthdays, work anniversaries, announcements and events, each
  card sized to its own content.
* Your leave: approved days per month over the last six months.
* HR managers additionally get: decisions waiting on them, a Today row that
  reports staleness instead of printing zeros, department and capacity
  figures, hiring pipeline, joiners and leavers, and the data gaps behind
  those numbers.

Optional panels degrade instead of failing
------------------------------------------
Announcements need hr_reward_warning and Events needs the event module.
Neither is a dependency: each is queried only when its model is present, and
the panel explains itself when it is not. Work anniversaries behave the same
way with joining_date, which comes from xn_auditree_erp.
    """,
    "version": "17.0.2.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "hr_holidays",
        "hr_attendance",
        "hr_recruitment",
        "hr_timesheet",
    ],
    "data": [
        "data/xn_dashboard_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "xn_hr_dashboard/static/src/scss/xn_dashboard_app.scss",
            "xn_hr_dashboard/static/src/js/xn_dashboard_app.js",
            "xn_hr_dashboard/static/src/xml/xn_dashboard_app.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
