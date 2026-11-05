# -*- coding: utf-8 -*-
{
    "name": "Auditree Joiner and Leaver Checklists - IT Helpdesk",
    "summary": "Starting a joining or exit checklist raises the IT helpdesk "
               "ticket for HR.",
    "description": """
Glue between xn_joiner_leaver and xn_it_helpdesk; installs itself when both
are installed.

Steps marked "Raises an IT ticket" (HR's request to IT for a joiner, and the
exit notice for a leaver) create a ticket in the IT Helpdesk, raised in HR's
name, when the checklist starts. The step is then done, which dates IT's
follow-on steps.
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "xn_joiner_leaver",
        "xn_it_helpdesk",
    ],
    "data": [
        "data/jl_step_data.xml",
        "views/views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": True,
}
