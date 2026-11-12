# -*- coding: utf-8 -*-
{
    "name": "Auditree Activity Tracking - Joiner and Leaver Steps",
    "summary": "Adds the activity-agent steps to the joining and exit "
               "checklists.",
    "description": """
Glue between xn_activity and xn_joiner_leaver; installs itself when both are
installed.

* Joining: IT installs the activity agent and confirms the laptop reports,
  the working day after the joining date.
* Leaving: IT removes the agent from the returned laptop.

Collection also stops on its own when the employee is archived.
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "xn_activity",
        "xn_joiner_leaver",
    ],
    "data": [
        "data/jl_step_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
