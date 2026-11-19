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

Days older than the oldest stored slot (summaries are kept longer than the
5-minute data) cannot be rebuilt: a rebuild leaves their metrics alone and
only updates the note. Re-linking and category changes therefore do not
reach those days. Existing rows are updated in one batched SQL `UPDATE`
(`_xn_write_rows`), not one ORM write per row -- keep `_UPDATE_COLUMNS` in
step with `_xn_vals()` when adding a field to the summary.

## Linking and exclusions

- UPN (`whoami /upn`) matched to `hr.employee.work_email`, then the
  employee's *Windows User Name* field. Unmatched data is kept under the raw
  sign-in and shows as "Not Linked".
- *Work Accounts Only* (Agent Setup, off by default, 17.0.1.6.0): only a
  UPN matching an employee's work email is stored. Local Windows accounts
  and unknown UPNs are dropped (the server still answers 200, so every agent
  version clears its queue), the laptop counts as reporting, and Devices
  shows the refused name in *Rejected Sign-in* / *Rejected At*. The
  *Windows User Name* field is not used while it is on. Already stored data
  is not touched.
- Never stored: *Exclude from Activity Tracking* (partners/directors) and
  `employee_type = 'system'` (shared mailboxes). Ticking the box deletes what
  was stored. Archived employees: new data is dropped, history is kept.

## Access

- Activity Tracking: View All Employees (`group_xn_activity_viewer`): all
  reports, devices, app usage, timelines, dashboard, read-only. HR Officers
  get it automatically (implied).
- Activity Tracking: Board of Directors (`group_xn_activity_board`, implies
  View All Employees): also sees the names in the dashboard's *Worth a
  conversation* panel. No HR group implies it, so HR does not. Give it in
  Settings > Users. Migration 17.0.1.4.0 moved everyone who had View All
  Employees without HR rights into it.
- HR Officer: View All Employees, can add notes for anyone, and the
  dashboard's *To sort out* panel.
- HR Manager: plus Agent Setup, app classification, overrides, view log.
- Activity Agent: Agent Installer (`group_xn_activity_installer`, own
  category so the viewer/board dropdown stays one field): for IT. Activity >
  Agent Installer downloads `install.ps1` (no settings, no key changes) and
  Activity > Devices is readable. No activity reports beyond their own.
- Reporting manager (no group): the "own and team" record rules on days,
  slots and the usage view cover everyone below them in the org chart
  (`employee_id child_of user.employee_ids`), so the dashboard, Team
  Timeline and day detail show their team. Opening a report's detail is
  logged. Devices stay viewer-only; the dashboard shows the team's laptops
  through sudo, name and state only.
- Employee: My Activity (own days and slots), own day notes, and the
  dashboard for themselves.
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
and idle threshold embedded; Agent Installers get the same file from
Activity > Agent Installer. Endpoint Central: Computer Configuration >
Custom Script, run as SYSTEM:

    powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Uninstall

Files go to `C:\ProgramData\XnActivity\` (Users: read/execute only); a
scheduled task for BUILTIN\Users starts it at logon and every 15 minutes;
the per-session mutex keeps one copy. Queue and log:
`%LOCALAPPDATA%\XnActivity\`. Sign the script with the internal
code-signing certificate and add a Defender/EDR exclusion for the folder.

## Calls and reading

- Agent (1.1+): no input but the microphone in use (Windows'
  CapabilityAccessManager registry: LastUsedTimeStop = 0) -> the sample is
  active, not idle. Checked only when the user would otherwise be idle.
- App flag *Count Idle as Active* (App Classification): idle time with that
  app in front is reported as active; applies to past days. Teams and Zoom
  set by default (migration 17.0.1.2.0 for existing databases).
- Agent (1.2+): when the window in front belongs to ApplicationFrameHost
  (Store apps: Photos, Settings, Calculator, To Do) the app's own process is
  reported instead of "Windows app frame". Needs the new installer on each
  laptop; 1.1 agents keep reporting the frame host.

## 5-Minute Detail

The Detail button on a day opens `xn.activity.app.usage` (the SQL view
behind App Usage), not the raw slots: grouped by category then app, largest
time first (`default_order="active_hours desc"` also orders the groups), and
idle time of *Count Idle as Active* apps shown as active, so the footer
matches the day row. Apps flagged *Windows / System* (lock screen, Start
menu, File Explorer, ...; set from `SYSTEM_APPS` when first seen, migration
17.0.1.4.0 for existing apps) fold into one *Windows / System* group unless
classified Productive or Unproductive; the filter *Hide Windows / System*
drops them, and Group By *Hour* shows when the time was spent. Employees
read their own rows of the view (same rules as the slots).

## Timelines

- **Day form** (`xn_activity_day_timeline` widget): one bar for the day,
  5-minute blocks coloured by state -- the category of the main app
  (Productive, Neutral, Unclassified, Unproductive, Windows / System), Idle,
  Locked -- with gaps where the laptop sent nothing. Hover a block for the
  time, top 3 apps and active/idle/locked.
- **Activity > Team Timeline** (activity viewers): the same bar, one row per
  person for a date, with department filter, previous/next day, screen and
  productive totals; a name opens the day.
- Data: `xn.activity.day.xn_timeline_data` / `xn_team_timeline`
  (`models/activity_timeline.py`), read through `xn.activity.app.usage` as
  the current user, so record rules decide whose rows come back. Minutes
  are laptop-local. Window: 08:00-20:00, widened to fit the data.
- Drawn with CSS boxes (`static/src/timeline/`), no Chart.js. A component
  getter must not be called `window`: OWL templates read `window` as the
  browser global (the bars rendered empty until renamed `bounds`).

## Dashboard

Activity > Dashboard (`xn_activity_dashboard`, menu for every internal
user). This week / last week / this month, compared with the period before;
department filter. Data: `xn.activity.day.xn_dashboard_data`
(`models/activity_dashboard.py`), read as the current user, so the scope is
the record rules' (all / team / self, shown under the title).

- Headline figures, averages per person by day, where screen time goes, by
  department, today's timeline, laptops, top apps. Averages and "days on
  target" count working days with screen time and no time off.
- *Worth a conversation* (names of people under half the target on 3+
  working days, with day notes): sent by the server only to the Board of
  Directors; everyone else sees the count in the headline figures.
- *Long days* (out-of-hours on 3+ days): a count, no names.
- *To sort out* (new unclassified apps, unlinked sign-ins, missing
  monitoring notice): HR only.
- A newer request always wins over a slower earlier one (`loadToken`), so
  the period buttons and the figures cannot disagree.
- The weekly digest email still names people under target and goes to HR
  Managers (or *Weekly Digest To*); it is not covered by the board-only rule.

## Crons

- *Activity: delete data past retention* -- nightly; slots after 180 days,
  summaries after 730 (Agent Setup).
- *Activity: alert on laptops not reporting* -- weekdays 10:00 IST. **Sends
  real email** (to *Laptop Alerts To*, else the digest recipients), once per
  laptop per silence of 2+ working days; cleared when it reports again.
  Archive retired laptops in Devices.
- *Activity: weekly digest to HR* -- Mondays 08:30 IST. **Sends real email**
  (to *Weekly Digest To*, else every HR Manager). Archive the outgoing mail
  server before testing on a prod copy.

## Joiner / leaver

`xn_activity_joiner_leaver` (auto-installs with `xn_joiner_leaver`) adds an
IT step to each checklist: confirm the agent reports (day after DOJ), remove
it from the returned laptop.

## Known issues (review 2026-11-17)

Found by reading the code. Fixed since, and verified on a copy of the test
database (17.0.1.4.0): the holiday timezone and slow reclassification
(a76ce4a); new employees not relinked (#1, `create` override); one bad slot
blocking the queue (#2: the server skips malformed slots and reports
`skipped`; agent 1.2 drops a batch on 400/413); unique-constraint 500s under
concurrent ingest (#3: SQL `ON CONFLICT` for day rows and apps, which turns
the clash into a serialization failure that Odoo retries -- the body is read
with `get_data(cache=True)` so the retry can read it again -- plus a random
0-2 minute delay before posting); the stuck microphone (#5: the app must be
running and the call started within 12 hours); the fixed 15 s credit (#8);
the `clock_offset` overflow and `Infinity` (#11).

Still open:

4. **Metrics can be faked by the employee.** `agent.ps1` (with the single
   shared API key) is readable by Users, the server trusts the `upn` in the
   body, and `queue.json` is user-writable. An agent in the user's session
   cannot fully hide a secret; mitigations are binding a device to the first
   UPN it reports and flagging new device/UPN pairs. Treat the numbers as
   indicative, not disciplinary evidence.
6. Stale-laptop alert counts Mon-Fri only (`_working_days_back`), so a
   multi-day public holiday flags every laptop. Use the company calendar.
7. Half-day leave is graded against the full productive target.
9. The view log covers only the Detail button; App Usage and the timelines
   show per-person detail unlogged.
10. HR Managers can unlink slots, but that does not rebuild the day row.
12. Ticking Exclude deletes history immediately, with no confirmation.
13. No tests; `_validate`, `_status`, `_xn_vals`, `_xn_schedule` are easy to
    cover.
