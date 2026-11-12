# xn_activity -- Daily Work Metrics from Windows laptops

Requirements: "Employee Activity Tracking in Odoo - Requirements v2" (Claude Docs).

## What it does

A PowerShell agent (`data/agent/agent.ps1`) runs hidden in each signed-in
user's session. Every 15 s it records active / idle / locked and the
foreground process name; every 5 min it POSTs the closed slots to
`/xn_activity/ingest`. Odoo stores them in `xn.activity.slot` and rebuilds
the per-person-per-day summary `xn.activity.day`.

Collected: process names and seconds. Never titles, URLs, keystrokes,
clipboard or screenshots.

## Models

| Model | What |
|---|---|
| `xn.activity.app` | Program (process name), category; `rule_ids` = per-department overrides (`xn.activity.app.rule`) |
| `xn.activity.slot` | Raw 5-minute rows. Written only by the ingest endpoint (SQL upsert, unique on device + sign-in + start + app) |
| `xn.activity.day` | Stored daily summary. Rebuilt by `_xn_recompute(pairs)`; `day_key` = `emp:<id>` when linked, else the raw sign-in |
| `xn.activity.note` | Day notes (client visit, offline work) |
| `xn.activity.device` | One row per computer: last seen, agent version, clock offset, rate limit counters |
| `xn.activity.view.log` | Who opened another person's 5-minute detail |
| `xn.activity.app.usage` | SQL view for the App Usage pivot (effective category) |
| `xn.activity.setup` | Agent Setup wizard; settings live in `ir.config_parameter` `xn_activity.*` |

When the summary is rebuilt: on every upload (affected days only), when an
app's category or a department override changes (every day using that app),
when a note changes, and when an employee's work email / Windows user name
changes (re-link). Changing the productive target re-grades all rows in SQL.

## Linking and exclusions

- UPN (`whoami /upn`) matched to `hr.employee.work_email`, then the
  employee's *Windows User Name* field. Unmatched data is kept under the raw
  sign-in and shows as "Not Linked".
- Never stored: *Exclude from Activity Tracking* (partners/directors) and
  `employee_type = 'system'` (shared mailboxes). Ticking the box deletes what
  was stored. Archived employees: new data is dropped, history is kept.

## Access

- Activity Tracking: View All Employees (`group_xn_activity_viewer`): all
  reports, devices, app usage, read-only. For the board of directors; give
  it in Settings > Users. HR Officers get it automatically (implied).
- HR Officer: the above, and can add notes for anyone.
- HR Manager: plus Agent Setup, app classification, overrides, view log.
- Employee: My Activity (own days and slots) and own day notes.
- Notes can be changed only by their author.

## Ingest endpoint

`POST /xn_activity/ingest`, header `X-Activity-Key`. 403 bad key, 400
malformed, 413 over 1 MB, 429 over 60 requests/hour per device. The previous
key keeps working for the grace period after *Generate New Key*. Response
carries `idle_seconds`, which the agent adopts.

Prod notes: nginx `client_max_body_size` must be at least 1m (default is
1m). `auth='public'` relies on prod's single-database `dbfilter`.

## Deploying the agent

Agent Setup > *Save and Download Installer* gives `install.ps1` with URL, key
and idle threshold embedded. Endpoint Central: Computer Configuration >
Custom Script, run as SYSTEM:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Uninstall

Files go to `C:\ProgramData\XnActivity\` (Users: read/execute only); a
scheduled task for BUILTIN\Users starts it at logon and every 15 minutes;
the per-session mutex keeps one copy. Queue and log:
`%LOCALAPPDATA%\XnActivity\`. Sign the script with the internal
code-signing certificate and add a Defender/EDR exclusion for the folder.

## Crons

- *Activity: delete data past retention* -- nightly; slots after 180 days,
  summaries after 730 (Agent Setup).
- *Activity: weekly digest to HR* -- Mondays 08:30 IST. **Sends real email**
  (to *Weekly Digest To*, else every HR Manager). Archive the outgoing mail
  server before testing on a prod copy.

## Joiner / leaver

`xn_activity_joiner_leaver` (auto-installs with `xn_joiner_leaver`) adds an
IT step to each checklist: confirm the agent reports (day after DOJ), remove
it from the returned laptop.
