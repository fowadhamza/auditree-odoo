# Auditree Recruitment Bridge

Lets the WordPress site at auditree.com list Odoo's open vacancies and file
job applications straight into Odoo recruitment.

## Why this rather than XML-RPC

The obvious way to connect WordPress to Odoo is to give WordPress an Odoo
login and let it call XML-RPC. That means a web server on someone else's
infrastructure holding credentials that can read every model in the database,
including HR records, payroll and employee personal data. WordPress
installations get compromised routinely; that should not escalate into an HR
data breach.

This module gives WordPress exactly one capability -- file a job application
-- behind one rotatable secret, with every field validated on the Odoo side.
The blast radius of a stolen token is spam applicants, not data loss.

## Endpoints

| Route | Auth | Purpose |
|---|---|---|
| `GET /auditree/recruitment/jobs` | public | Published vacancies as JSON |
| `GET /auditree/recruitment/ping` | token | Connectivity/credential check |
| `POST /auditree/recruitment/apply` | token | Creates an `hr.applicant` |

`/jobs` is public on purpose: it serves the same records core already
publishes at `/jobs`, so authenticating it would protect nothing.

### The shared secret

Generated at install into the system parameter
`xn_recruitment_bridge.api_token`. There is no default and no fallback -- if
the parameter is missing or empty, `/apply` refuses every request rather than
running open.

Read it at **Settings > Technical > System Parameters**. Rotate it by editing
that value and updating the WordPress end. Re-running `-u` on this module
never overwrites an existing token.

WordPress sends it as an `X-Auditree-Token` header; it is compared with
`hmac.compare_digest`.

### POST /auditree/recruitment/apply

`multipart/form-data`, because a CV has to fit in the request.

| Field | | Notes |
|---|---|---|
| `job_id` | required | Must be an `is_published`, active `hr.job` |
| `name` | required | Whitespace collapsed, capped at 256 chars |
| `email` | required | Must survive `tools.email_normalize` |
| `phone` | optional | Capped at 32 chars to match the column |
| `linkedin` | optional | |
| `letter` | optional | Plain text; escaped through `plaintext2html` |
| `cv` | optional | 10 MB cap, extension allowlist |

Responses are JSON with a meaningful status code:

* `200 {"status": "ok", "applicant_id": 6, "stage": "New"}`
* `200 {"status": "duplicate", "applicant_id": 6}` -- same email, same job,
  inside 90 days. Matches core's own recent-application window. Without this,
  a double-clicked submit button or a retrying WordPress plugin files the same
  person twice.
* `400 {"status": "error", "errors": {...}}` -- per-field validation
* `401` -- bad or missing token
* `413` -- CV over the size cap

## Decisions worth knowing before you change this

**Creation only; the bridge never sets a stage.** `hr.applicant.write` in
`xn_auditree_erp` sends approval email with `force_send=True` whenever
`stage_id` moves. An endpoint that could set a stage would also be a way to
make Odoo send mail on demand from the public internet. The stage is left to
core's `_compute_stage`, which picks the first unfolded stage for the job --
"New" in this database.

**`is_published` is load-bearing on the jobs feed.** `hr.job` holds 34 records
here, most of them employee job titles (CEO, CFO, Partner, Consultant) rather
than open vacancies, because Odoo reuses the model for both. An unfiltered
feed would advertise a vacancy for every role in the company. Only 4 records
are currently published.

**An unpublished job is reported as "unknown or closed", not "closed".**
Distinguishing the two would confirm valid ids to someone enumerating them.

**Cover letters go through `plaintext2html`.** `description` is an HTML field
and the text arrives from the public internet, so it is escaped rather than
trusted. A cover letter cannot carry markup into a recruiter's browser.

**The CV extension allowlist is an allowlist, not a blocklist.** Anything not
in `ALLOWED_CV_EXTENSIONS` is refused rather than stored for someone to click
on later.

**No rate limiting here.** That belongs in nginx in front of Odoo, not in a
worker process. The duplicate guard limits the damage in the meantime. If
this endpoint gets abused, rate-limit `location /auditree/` in the vhost.

## Verified

Exercised against local Odoo on 2026-09-18, all cases confirmed by HTTP
response and by querying the database afterwards:

* jobs feed returns exactly the 4 published jobs
* ping rejects missing and wrong tokens (401), accepts the right one
* apply rejects no token (401), missing name/email (400), malformed email
  (400), an unpublished `job_id` (400) and a `.exe` upload (400)
* a valid submission creates the applicant in stage New, sourced
  "auditree.com Careers", with the name whitespace-collapsed, the email
  normalised to lowercase, the CV attached and set as the main attachment
* `<script>` in the cover letter is stored escaped
* resubmitting the same email/job returns `duplicate` without creating a
  second record; the same person applying to a *different* job does create one
* no row is added to `mail_mail` -- confirming no approval email fires

Test applicants were removed afterwards.

## Not done yet

The WordPress end. `wordpress/auditree-odoo-recruitment.php` in this module is
a complete, self-contained plugin, but it has not been run against a real
WordPress install -- the form plugin in use on auditree.com is still unknown.
Treat it as a starting point to verify on staging, not as tested code.
