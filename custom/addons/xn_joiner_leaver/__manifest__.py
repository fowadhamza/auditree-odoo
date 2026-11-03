# -*- coding: utf-8 -*-
{
    "name": "Auditree Joiner and Leaver Checklists",
    "summary": "Joining and exit steps as tasks with owners, due dates, proof, "
               "a daily reminder digest and escalation, instead of email chasing.",
    "description": """
When HR starts a joining checklist (once the BGV report is green and the date
of joining is fixed) or an exit checklist (when a resignation or termination
arrives), Odoo creates one task per step for HR, IT, Admin, Accounts and the
reporting manager, each with a due date.

* Steps are dated from the start, from the joining date / last working day,
  or from when the previous step is done (the exit checklist sign-offs run in
  sequence, 2 working days each).
* Each working morning everyone with open steps gets one digest email: due
  today and overdue.
* A step 2 working days overdue is escalated to the Operations Manager in a
  daily digest. Steps waiting on outside parties (candidate, leaver, courier)
  are never escalated.
* Access not disabled by the evening of the last working day alerts IT and
  the Operations Manager the same evening.
* Steps that need proof cannot be marked done without an attachment.

The steps and who does them are configuration (Joiners & Leavers >
Configuration).
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "project",
        "mail",
        "resource",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/project_data.xml",
        "data/jl_role_data.xml",
        "data/jl_step_data.xml",
        "data/ir_cron_data.xml",
        "data/mail_templates.xml",
        "views/jl_step_views.xml",
        "views/jl_checklist_views.xml",
        "views/project_task_views.xml",
        "views/hr_employee_views.xml",
        "views/jl_menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
