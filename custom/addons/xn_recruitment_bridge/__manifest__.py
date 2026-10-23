# -*- coding: utf-8 -*-
{
    "name": "Auditree Recruitment Bridge",
    "summary": "Authenticated HTTP endpoints so the auditree.com WordPress site "
               "can list open jobs and file applications directly into Odoo "
               "recruitment.",
    "description": """
Lets the WordPress marketing site at auditree.com act as the front end for
Odoo recruitment, without exposing Odoo's RPC interface to the internet.

Two endpoints
-------------
* GET  /auditree/recruitment/jobs   -- published, active vacancies as JSON.
  Public, because this is the same data core already serves at /jobs.
* POST /auditree/recruitment/apply  -- creates an hr.applicant, with an
  optional CV attachment. Authenticated by a shared secret.

Why an endpoint and not XML-RPC
-------------------------------
Pointing WordPress at Odoo's XML-RPC would mean a web server on someone
else's infrastructure holding credentials that can read every model in the
database, HR records included. A WordPress compromise is a common event; it
should not become an HR data breach. This module gives WordPress exactly one
thing it can do -- file a job application -- behind one rotatable secret,
with every field validated on the Odoo side.

The shared secret
-----------------
Stored in the system parameter 'xn_recruitment_bridge.api_token', generated
at install time. There is no default value and no fallback: if the parameter
is missing or empty the apply endpoint refuses every request rather than
running open. Rotate it by editing the parameter in Settings > Technical >
System Parameters and updating the WordPress end.

Deliberately not included
-------------------------
* No update or read of existing applicants. Creation only. Stage changes in
  this database send approval email synchronously (see xn_auditree_erp), so
  an integration that could move stages could also send mail from the
  outside.
* No rate limiting. That belongs in nginx in front of Odoo, not in a
  worker process. The duplicate guard below limits the damage in the
  meantime.
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "hr_recruitment",
        "website_hr_recruitment",
        "utm",
    ],
    "data": [
        "data/xn_recruitment_bridge_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
