# -*- coding: utf-8 -*-
{
    "name": "Auditree IT Helpdesk",
    "version": "17.0.1.2.0",
    "category": "Services/Helpdesk",
    "summary": "IT tickets for employees, run by the IT team. "
               "Built on OCA helpdesk_mgmt.",
    "description": """
IT Helpdesk on top of the OCA Helpdesk Management module
========================================================

helpdesk_mgmt is installed untouched; everything Auditree-specific lives here.

Requesters ("Raise IT Tickets" group)
-------------------------------------
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

Management approval
-------------------
* IT clicks Request Approval, picks the approver (the team's Default
  Approver is suggested) and says what needs approving. The ticket moves to
  Pending Approval and the approver gets an email with a link.
* The approver opens the ticket (or IT Helpdesk > To Approve) and clicks
  Approve or Reject; a reason is required to reject. No Helpdesk rights
  needed: a record rule lets approvers read the tickets they are asked about.
* Approved: back to In Progress (New if unassigned) for IT to carry out.
  Rejected: resolved as not approved, so the employee gets the Resolved
  email with the reason. IT (whoever asked, the assignee, the IT team) is
  emailed either way. IT can withdraw a pending request.
* While pending, the ticket cannot leave Pending Approval any other way,
  and cannot be moved into it without a request.
* Every request is a row in the ticket's Approval tab: requested by / on,
  approver, what needed approval, outcome, decided by / on, comments. Rows
  cannot be edited or deleted, and a ticket with approval history cannot be
  deleted.

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
        # Groups first: the access CSV references the requester group.
        "security/xn_it_helpdesk_security.xml",
        "security/ir.model.access.csv",
        "data/mail_template_data.xml",
        "data/helpdesk_data.xml",
        "data/ir_cron_data.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_ticket_stage_views.xml",
        "views/helpdesk_ticket_report_views.xml",
        "views/helpdesk_approval_views.xml",
        "views/menus.xml",
        "views/portal_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
