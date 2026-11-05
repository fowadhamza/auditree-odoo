# Auditree Joiner and Leaver Checklists (`xn_joiner_leaver`)

Joining and exit steps as dated tasks for HR, IT, Admin, Accounts and the reporting manager,
with one daily reminder email per person and escalation to the Operations Manager. Replaces
the email chasing described in `docs/joiner-leaver-answers.md` (feature 1 of
`docs/odoo-features-from-kra-register.md`).

Depends on core `hr`, `project`, `mail`, `resource` and on `hr_resignation` (installed on prod).
`xn_joiner_leaver_helpdesk` installs itself alongside `xn_it_helpdesk` and raises the IT tickets.

## How it works

- **Start.** HR starts a checklist from the employee form (*Start Joining Checklist* /
  *Start Exit Checklist*) or from *Joiners and Leavers > Checklists*.
  - Joining: once the BGV report is green and the date of joining (DOJ) is fixed. The offer,
    documents and BGV stay on the applicant (`xn_recruitment`). The date defaults to the
    employee's `joining_date` when `xn_auditree_erp` provides one.
  - Exit: when the resignation or termination arrives; the date is the last working day
    (LWD). Exit type: resignation, termination, or immediate termination. **Approving a
    resignation** (*Resignation* menu) starts it automatically, with the approved LWD
    (confirmation date plus the contract notice days), unless one is already running.
  - A joining date fewer than 10 working days away (`JOIN_NOTICE_DAYS`) warns HR on the
    form: IT needs that much notice.
- **Steps** (`xn.jl.step`, *Configuration > Checklist Steps*) become one `project.task`
  each in the private *Joiners and Leavers* project. A step is dated:
  - from the start (`start`, N working days after the checklist is created),
  - from the DOJ / LWD (`date`, negative = before), or
  - from when another step is done (`after`). These have no due date until then. The exit
    checklist sign-offs (manager, Admin, IT, Accounts, HR, Operations Manager) run this way,
    2 working days each, starting once IT confirms the returned assets.

  Due dates are never before the start date. For an immediate termination every step not
  waiting on another is due today.
- **Owners** come from the step's role. *Configuration > Who Does What* (`xn.jl.role`)
  maps HR, HR Head, Operations Manager, IT, Admin and Accounts to users. Reporting Manager
  is the employee's manager. An empty role, or a manager without a user, falls back to HR.
  A step can also have *Also Visible To*: that role follows the step (the HR Head on
  agreeing the LWD) and is notified about it.  Owners without Project > User get it when their first step is created (logged on the
  checklist).
- **Working days** use the company's working-hours calendar (weekdays plus its public
  holidays).
- **Proof.** A step with *Proof* set cannot be marked done without an attachment (bypassed
  for superuser/cron).
- **Re-dating.** Changing the checklist date moves every open `date` step.
  *Cancel Checklist* (joiner did not join, resignation withdrawn) cancels the open steps.
  The checklist closes itself when every step is done or cancelled.

## Reminders and escalation

| Cron | When | What |
|---|---|---|
| Daily digest and escalation | 09:15 IST, working days | One email per owner listing their steps due today or late. Steps late by at least `escalate_after` working days (minimum 1) are flagged *Escalated* and listed in one email to the Operations Manager, every day until done. |
| Evening alert | 19:00 IST | Steps marked *Urgent* (disabling access on the LWD) still open on their due date: one email to the owner and the Operations Manager, once per step. |

Steps marked *Waits on Someone Outside* (candidate, leaver, courier) are reminded to their
owner but never escalated. Emails go out from `xn_joiner_leaver.email_from` (system
parameter, default `hr@auditree.com`) via the mail queue. **They are real email.** Archive
the outgoing mail server before testing on a prod copy.

## Install notes

- `post_init_hook` fills every role from `ROLE_LOGINS` in `__init__.py` (IT = `it@`, Admin =
  mohammed.junaid@), gives those users Project > User, and makes HR and the Operations
  Manager followers of the project so they see every step. Project Administrators (on prod:
  Sharook and `it@`) see every step regardless.
- Seeded steps (`data/jl_step_data.xml`, `noupdate`): HR's process, plus KRA-register
  deadlines for IT, Admin and Accounts (confirmed Nov 2026).
  Edit them in the UI; an upgrade does not overwrite them.
- Tasks key off `project.task.xn_jl_checklist_id` / `xn_jl_step_id`, not names or stages.
- Steps open in their own form (`view_task_form_xn_jl_step`), also from the email links.
  The standard task form carries `bi_crm_task`'s invoice totals, which raise an Access
  Error for anyone without accounting rights (IT, Admin) -- on any task, not only these.
- The short-notice warning is a banner on the form, not an onchange warning: a warning
  raised while the Start Joining Checklist dialog loads stops the dialog opening.

## IT tickets (`xn_joiner_leaver_helpdesk`)

Steps with *Raises an IT Ticket* (HR's IT request for a joiner, the exit notice for a
leaver) create an IT Helpdesk ticket in HR's name when the checklist starts (category
Access Request; High for an immediate termination) and are marked done, which dates IT's
follow-on steps. The ticket sends the usual helpdesk emails.

## Not done yet

- No automatic start when an applicant is hired (still open: start at BGV green or at hire).
- Amber BGV (Management decides) belongs in recruitment, before the checklist.
- Rejecting or cancelling an approved resignation does not cancel the exit checklist; HR
  cancels it.
