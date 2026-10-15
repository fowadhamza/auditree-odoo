# -*- coding: utf-8 -*-
{
    "name": "Auditree IT Helpdesk",
    "version": "17.0.1.0.0",
    "category": "Services/Helpdesk",
    "summary": "IT tickets for employees, run by the IT team. "
               "Built on OCA helpdesk_mgmt.",
    "description": """
IT Helpdesk on top of the OCA Helpdesk Management module
========================================================

helpdesk_mgmt is installed untouched; everything Auditree-specific lives here.

Employees (any internal user)
-----------------------------
* Raise tickets from IT Helpdesk > My Tickets. Name, employee ID, email and
  department are filled in from their employee record.
* See only their own tickets, reply and attach files from the chatter,
  confirm a resolution or reopen the ticket.
* Never see internal IT notes ("Log note" in the chatter) or the files
  attached to them.

IT team (Helpdesk groups from helpdesk_mgmt)
--------------------------------------------
* "User" sees and manages every ticket; "Helpdesk Manager" also gets
  Configuration (categories, stages, teams, settings).
* Assign and reassign, move between New / In Progress / On Hold / Resolved /
  Closed. Resolution notes are mandatory before Resolved or Closed.
* Dashboard tiles per status, filters by date / employee / category /
  priority / status / assignee, and an ageing + resolution-time report.

Notifications
-------------
* Employee: acknowledgement on submission, an email on every status change
  (with the resolution details when resolved), and every IT reply.
* IT team: every new ticket; the assignee on assignment (standard Odoo).
* Replies happen in Odoo only; there is no incoming-mail alias.

Other rules
-----------
* Resolved tickets close themselves after 3 days without a confirmation or
  reopen (system parameter xn_it_helpdesk.autoclose_days; 0 turns it off).
* Shared mailbox logins (employee type Shared / System Account) cannot see
  the app or raise tickets, except it@auditree.com, which is on the IT team.
* helpdesk_mgmt's website pages (/my/tickets, /new/ticket) redirect to the
  backend app.
""",
    "author": "Auditree",
    # AGPL to match helpdesk_mgmt, which this module extends.
    "license": "AGPL-3",
    "depends": ["helpdesk_mgmt", "hr", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "security/xn_it_helpdesk_security.xml",
        "data/mail_template_data.xml",
        "data/helpdesk_data.xml",
        "data/ir_cron_data.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_ticket_stage_views.xml",
        "views/helpdesk_ticket_report_views.xml",
        "views/menus.xml",
        "views/portal_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
