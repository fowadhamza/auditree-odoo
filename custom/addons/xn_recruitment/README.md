# xn_recruitment -- Auditree hiring process

Extends the core Recruitment app (`hr_recruitment`) with the process HR described in
the October 2026 questionnaire. Tier 1 (in-house): edit freely.

## How it hangs together

| Piece | Where |
|---|---|
| Hiring steps | `hr.recruitment.stage.xn_round` (`models/hr_recruitment_stage.py`). Logic keys off the step, never stage names or ids. `ROUNDS` defines the order. |
| Interview panels | `xn.recruitment.panel` + `.line` (round -> users); `hr.job.xn_panel_id`. |
| Handover email | `hr.applicant._xn_handover_to_interviewers`, called from `write()` when a candidate moves **forward** into `round1`/`round2`/`final`/`decision`. Adds the panel as `interviewer_ids` (that is what gives Interviewer-only users access), emails them from HR with the CV files and the previous round's feedback, schedules a 1-day to-do. Body: `views/mail_templates.xml`. |
| Feedback | `xn.applicant.feedback`; "Give Feedback" button on the applicant. Rules in `security/xn_recruitment_security.xml`. |
| Rejection email | Not code: every refuse reason (`data/xn_recruitment_data.xml`) carries `mail_template_candidate_rejection`, and the core Refuse wizard sends a reason's template. Stock reasons are archived by the hook. |
| Reapplication | `_xn_check_reapplication` on create (skip with context `xn_skip_reapply_check`, e.g. for imports). |
| Reports | `xn.recruitment.position.report` / `.source.report` (SQL views, `-u` to change), `xn.applicant.stage.log` (one row per stage move). Counts use `hr.applicant.xn_max_round_order`, the furthest step ever reached. |
| Daily email | `ir_cron_daily_hiring_report`, installed **inactive**; recipients in system parameter `xn_recruitment.daily_report_emails`. |

`post_init_hook` (install only) maps existing stages by name and creates missing ones,
fills the panels by first name (Usama, Keerthana, Athif, Faraz / Ayesha, Nishath,
Sharook, Fowad -- ambiguous names are logged and skipped), gives audit jobs the
Technical panel and the rest Non-Technical, seeds sources and the two active agencies,
and backfills `xn_max_round_order` from current stages.

## Before testing on a local copy of production

The local database is a copy of prod and still has prod's outgoing mail server. Moving
a candidate or refusing one **will email real interviewers and candidates**. Archive
the outgoing mail server first (Settings > Technical > Outgoing Mail Servers), or:

```sql
UPDATE ir_mail_server SET active = false;
```

## Sender address

Templates and handover emails use `hr@auditree.com` (system parameter
`xn_recruitment.hr_email`). Production's only outgoing server is Titan with From
filtering `no-reply@auditree.org`, so Odoo rewrites any other sender to that address.
To really send as hr@auditree.com, add an outgoing server that may send for
auditree.com (Microsoft 365: `smtp.office365.com`, port 587, STARTTLS, a mailbox with
"Send As" on hr@, FROM filtering `auditree.com`).

## Moving candidates

`xn_auditree_erp` makes the stage bar read-only and moves candidates with "Approve And
Move To Next", which goes to the stage whose sequence is current + 1. The hook numbers
HR's stages 1..9 consecutively so that button walks the rounds in order; keep the
sequences consecutive if stages are added.

## Not done yet (phase 2)

CV intake from hr@ / job sites with automatic data filling, importing the 2025/2026
trackers, COO offer approval, agency fee and referral bonus due tracking.
