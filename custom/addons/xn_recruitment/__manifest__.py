# -*- coding: utf-8 -*-
{
    "name": "Auditree Recruitment",
    "version": "17.0.1.1.0",
    "category": "Human Resources/Recruitment",
    "summary": "Auditree's hiring process on Odoo Recruitment: interview rounds and "
               "panels, interviewer feedback, automatic emails, daily hiring reports.",
    "description": """
Auditree hiring process on top of the core Recruitment app
==========================================================

Built from HR's answers to the recruitment questionnaire (Oct 2026).

Process
-------
* Stages: New, Cold Call Shortlist, HR Initial Call, Round 1, Round 2,
  Final Round, Decision Making, Selected, Joined. Each stage carries a
  Hiring Step (hr.recruitment.stage.xn_round); logic keys off the step,
  never the stage name, so stages can be renamed.
* Interview panels per job (Technical / Non-Technical), one or more
  interviewers per round.
* Moving a candidate forward into an interview round: the round's
  interviewers become interviewers on the application (which opens it to
  Interviewer-only users), are emailed from HR with the CV attached and
  the feedback from the round just finished (no salary), and get a to-do
  to send feedback within a day.
* Give Feedback: comments plus a recommendation (next round / hold /
  reject). Posted on the application, the recruiter is pinged, the
  interviewer's to-do is closed.
* Refusing a candidate at any stage emails them: every refuse reason
  (HR's list) carries the rejection template, which the core Refuse
  wizard sends.
* Hold with a reason; refused candidates who reapply within 6 months are
  flagged and the recruiter gets a to-do.

Data
----
* Candidate: notice period, qualification, CA/ACCA papers, CA Final
  attempts, articleship, experience, location, current / expected /
  offered CTC (annual INR; hidden from interviewers), agency, referrer,
  bond, did-not-join.
* Job requisition: requested by, reason, CTC band, experience,
  qualification, joining requirement, deadline, panel.
* Agencies are contacts flagged Recruitment Agency with their fee rule.

Reports (Recruitment > Reporting)
---------------------------------
* Hiring Status: funnel per position, days open / to close.
* Daily Movement and Interviews: yesterday by position and round.
* Source Performance: CVs to joiners per source and agency.
* Optional daily email (scheduled action, installed inactive).
""",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": ["hr_recruitment", "mail", "utm"],
    "data": [
        "security/ir.model.access.csv",
        "security/xn_recruitment_security.xml",
        "data/mail_template_data.xml",
        "data/xn_recruitment_data.xml",
        "data/ir_cron_data.xml",
        "views/mail_templates.xml",
        "views/xn_recruitment_panel_views.xml",
        "views/xn_applicant_feedback_views.xml",
        "views/hr_recruitment_stage_views.xml",
        "views/hr_job_views.xml",
        "views/hr_applicant_views.xml",
        "views/res_partner_views.xml",
        "views/xn_recruitment_report_views.xml",
        "views/xn_recruitment_menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
