# -*- coding: utf-8 -*-
{
    "name": "Auditree HR Dashboard",
    "summary": "Organisation panels for the HRMS dashboard, and fixes for the "
               "birthday, event and announcement panels.",
    "description": """
Extends the Open HRMS dashboard (hrms_dashboard) rather than forking it.

Adds
----
* A "Today" row driven by attendance, which reports staleness instead of
  printing zeros when nobody has clocked in for weeks.
* A "Needs a decision" row that replaces the vendor's three approval tiles.
* Hiring pipeline by stage, project hours by month, attendance trend and a
  joiners/leavers panel that reads departure_date rather than resign_date.
* A "Gaps affecting this dashboard" panel.
* A work anniversaries panel beside the vendor's birthdays, computed from
  joining_date. Everyone sees it, not only HR managers.

Fixes in the vendor's own panels, by override rather than by patch
------------------------------------------------------------------
* get_dept_employee counted archived employees and dropped the unassigned.
* The birthday list included archived employees and required a job position.
* Announcements were headlined by their sequence code instead of their title.
* The event list required a venue, and had no empty state.
* The announcement query interpolated ids into SQL.
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "hrms_dashboard",
        "hr",
        "hr_attendance",
        "hr_holidays",
        "hr_recruitment",
        "hr_timesheet",
        "hr_reward_warning",
        "event",
    ],
    "data": [
        "data/xn_dashboard_action.xml",
    ],
    "assets": {
        # hrms_dashboard is a dependency, so its assets are ordered first and
        # the client action is already in the registry when this file runs.
        "web.assets_backend": [
            # The replacement dashboard, registered under its own action tag.
            "xn_hr_dashboard/static/src/scss/xn_dashboard_app.scss",
            "xn_hr_dashboard/static/src/js/xn_dashboard_app.js",
            "xn_hr_dashboard/static/src/xml/xn_dashboard_app.xml",
            # The vendor patches below are the rollback path: they are what the
            # old dashboard needs to be usable, and they still apply if the tag
            # in data/xn_dashboard_action.xml is put back to "hr_dashboard".
            "xn_hr_dashboard/static/src/scss/xn_dashboard.scss",
            "xn_hr_dashboard/static/src/js/xn_dashboard.js",
            "xn_hr_dashboard/static/src/xml/xn_dashboard_templates.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
