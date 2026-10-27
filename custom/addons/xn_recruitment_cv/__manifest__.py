# -*- coding: utf-8 -*-
{
    "name": "Auditree Recruitment - CV Reading",
    "version": "17.0.1.0.0",
    "category": "Human Resources/Recruitment",
    "summary": "Fill in an application's candidate details from the attached CV with AI.",
    "description": """
Reads the CV attached to an application (PDF, Word .docx or text) and fills
in the candidate details HR otherwise types by hand: name, email, phone,
LinkedIn, location, current employer and designation, qualification, CA /
ACCA papers, CA Final attempts, articleship, experience, notice period and
CTC when stated, plus a short summary for the interviewers.

* Only empty fields are filled. Where the CV disagrees with the
  application (name, email, phone) the field is left alone and the
  difference is listed in the chatter.
* Read CV button on the application (Recruitment Officers), and a
  scheduled job that reads CVs attached in the last two days, however
  they arrived (job email alias, website, chatter upload).
* All AI calls go through xn_ai_core: kill switch, monthly budget,
  request log. PAN and Aadhaar numbers are masked before sending.
* Scanned CVs have no text and are flagged for manual entry.
""",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": ["xn_recruitment", "xn_ai_core"],
    "data": [
        "views/hr_applicant_views.xml",
        "data/ir_cron_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
