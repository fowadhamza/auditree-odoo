# xn_hr_dashboard

**This module now renders the Dashboard.** It supplies a replacement client
action and its own OWL component, and reuses `hrms_dashboard` for its Python
endpoints only. No vendor file is edited, and none of the vendor's templates or
its stylesheet are rendered any more.

The switch is one field: `data/xn_dashboard_action.xml` sets the tag on the
vendor's `hr_action_dashboard` record to `xn_hr_dashboard`. The menu item, its
name, its icon and its groups are untouched.

## Why replace rather than keep patching

The vendor markup is Bootstrap 3 on a Bootstrap 5 platform. `col-xs-*`, `media`
and `media-body` were all removed in BS4 and do nothing in Odoo 17, which is
why its grid never aligned. On top of that its panels are pinned at 316px
regardless of content, its profile card is `position: fixed` and needs an empty
spacer column in every row to avoid being overlapped, it carries 37 inline
`style=` attributes, and its 1,004-line stylesheet is pulled in by a `<link>`
inside `LoginEmployeeDetails` so it loads after the asset bundle and wins every
tie at equal specificity.

None of that is reachable by overrides. Not rendering the template is what
unloads the stylesheet.

## Layout

```
+- Person strip ------------------------------------------------+
|  photo  name / job / department   [Payslips][Timesheets]      |
|                                   [Contracts][Broad factor]   |
|                                                   [Check in]  |
+---------------------------------------------------------------+
+- Your team ---------------------------------------------------+
|  Birthdays | Anniversaries | Announcements | Events           |
|  every card sizes to its own content                          |
+---------------------------------------------------------------+
+- Your leave --------------------------------------------------+
|  Days taken, last six months                                  |
+---------------------------------------------------------------+
   everything below is HR managers only
+- Needs a decision --------------------------------------------+
|  [Leave requests] [Leave allocations] [Live applications]     |
+---------------------------------------------------------------+
+- Today -------------------------------------------------------+
|  four figures, or a staleness notice when attendance stopped  |
+---------------------------------------------------------------+
+- Across the organisation ------------------ 28 active staff --+
|  [By department]    [Hours against capacity]                  |
|  [Attendance]       [Hiring pipeline]                         |
|  [Joiners and leavers]                                        |
+---------------------------------------------------------------+
+- Gaps affecting these figures --------------------------------+
```

## The replacement, file by file

| File | What it is |
|---|---|
| `static/src/js/xn_dashboard_app.js` | The OWL component, registered as action tag `xn_hr_dashboard`. Loads the endpoints and shapes every figure. |
| `static/src/xml/xn_dashboard_app.xml` | The whole page. Inherits nothing. |
| `static/src/scss/xn_dashboard_app.scss` | Tokens and layout, all scoped under `.xn_dash`. |
| `data/xn_dashboard_action.xml` | Points the existing action at the new tag. |

**No Chart.js.** Every chart is drawn from numbers computed in the component:
CSS boxes for bars and columns, one hand-built SVG path for the leave line.
Odoo 17 does not ship Chart.js in `web.assets_backend`, so the vendor's canvases
depended on a `loadBundle` that fails silently and leaves them blank. Removing
the library removes the failure mode, and there is no `onMounted` render step.

**No arithmetic in the template.** Widths, heights, percentages and chart
coordinates are all computed in `xn_dashboard_app.js`, so what is drawn and what
is counted cannot drift apart.

**Light theme only, but token-driven.** Odoo 17 Community has no dark mode to
hook into, so shipping dark rules would either be dead code or fire from
`prefers-color-scheme` inside a light Odoo shell. Every colour is a custom
property on `.xn_dash`; a dark theme later means redefining those tokens under
whatever selector a future theme stamps, and nothing else changes.

**No web fonts.** Figures use a monospace stack with `tabular-nums` so columns
line up; everything else inherits Odoo's own face. The ERP does not reach out
to Google Fonts.

## Rolling back

Set the tag in `data/xn_dashboard_action.xml` back to `hr_dashboard` and upgrade
the module. The vendor dashboard returns, complete with the `t-inherit` fixes in
`xn_dashboard_templates.xml` and `xn_dashboard.js`, which are still in the
bundle for exactly this reason. Those two files are dead code while the new
dashboard is active; delete them once the replacement has been in use long
enough to trust.

## The rules this module follows

**Say whose numbers these are.** The most common misread of the vendor
dashboard is taking the personal block for an organisation-wide one. Two
headings fix it more cheaply than any amount of tile redesign.

**A tile's count and the list it opens come from one domain.** `_xn_domains()`
returns the dict; `xn_dashboard_tiles` counts it and `xn_open_tile` opens it.
No domain is written twice, so a tile can never disagree with the list behind
it.

**A freshness flag is measured over the window it guards.** The vendor pattern
of `search_count([]) > 0` over all time is what lets a "Today" row print four
zeros three weeks after check-in stopped. `attendance_current` is computed from
the most recent check-in, and the template blanks the figures and names the
problem instead of rendering zeros.

**Every date window is bounded at both ends.** An unbounded "last 30 days"
counted 26 future-dated timesheet lines on this database and reported 858 hours
where the honest figure was 650.

**No chart has two y-scales.** Attendance hours and people clocking in are
different units and get one plot each.

## Vendor defects this module corrects, by override

| Vendor behaviour | Fix |
|---|---|
| `get_dept_employee` has no `active` filter and inner-joins `hr_department`: 52 counted against 28 active, and the unassigned vanish | overridden; returns the same shape with active staff and a "No department" slice |
| Birthday list includes archived employees and requires a job position | `get_upcoming` rewritten: `active` filter, `LEFT JOIN hr_job` |
| Announcements headline `name` (the sequence code) instead of `announcement_reason` (the title) | title first, code and validity as a metadata line |
| Event list inner-joins its venue, so venue-less events vanish; no empty state | `LEFT JOIN`, plus empty states on all three panels |
| Announcement query interpolates ids into SQL with `%` | single parameterised statement; also scoped to `env.companies` |
| Birthday avatar passes the whole result row to the image URL helper | `employee[0]` |
| `join_resign_trend` and `attrition_rate` read `resign_date`, populated on zero records here, so both always show zero | both removed; replaced by a joiners/leavers panel reading `departure_date` |

## Things worth knowing

* **`ACTION_TAG`** in `static/src/js/xn_dashboard.js` must match the `tag` on
  the vendor's `ir.actions.client` (`hr_dashboard`). If it ever stops matching,
  the module logs a warning and does nothing rather than breaking the dashboard.
* **Chart.js is not in `web.assets_backend`** in Odoo 17. It lives in
  `web.chartjs_lib`, which this module loads with `loadBundle` in
  `onWillStart`. Without that, every canvas stays blank and no error is raised.
* **Work anniversaries** come from `xn_work_anniversaries`, computed from
  `joining_date` over a 30-day window - wider than the birthday panel's 15,
  because 16 employees have a joining date and a fortnight is usually empty.
  `joining_date` belongs to `xn_auditree_erp`, which this module does not
  depend on, so the endpoint returns `tracked: False` and the panel says why it
  is empty rather than raising. The SQL adds `N * interval '1 year'` instead of
  using `make_date`, which raises on a 29 February joining date in a non-leap
  year. Anyone in their first year is excluded.
* **The vendor stylesheet beats this bundle at equal specificity.**
  `LoginEmployeeDetails` carries `<link href="/hrms_dashboard/static/src/css/
  hrms_dashboard.css"/>` inside the template, so it is appended to the DOM
  after `web.assets_backend` and wins every tie. Any rule here that overrides a
  vendor one needs more specificity, not just a later position: the
  anniversary panel's height is `.hr_notification.xn_anniversary_panel`, and a
  lone `.xn_anniversary_panel` silently loses.
* **The anniversary panel's xpath anchor** is
  `//div[hasclass('hr_notification') and not(hasclass('col-xs-12'))]`. All three
  vendor panels carry `hr_notification`; only the birthdays card lacks
  `col-xs-12`, so this picks it out without counting position.
* **Hire date** falls back `joining_date` -> `create_date`. 14 of 60 employees
  here have no `joining_date` (it is computed from contract start, and they have
  no contract); excluding them understated the attrition denominator.
* **Late arrival** means a check-in later than the earliest `hour_from` on that
  employee's own working schedule for that weekday, plus a grace period. Change
  it with the `xn_hr_dashboard.late_grace_minutes` config parameter (default 15).
* **Capacity** in the project-hours chart applies one company calendar to
  everyone rather than each employee's own. Accurate enough for a trend, not for
  billing.
* Org-wide methods use `sudo()` to match the vendor's behaviour, but each checks
  `hr.group_hr_manager` first, and the client does not call them at all for
  anyone else.

## Deliberately not built

Payroll and contract panels. One payslip and zero open contracts is not thin
data, it is an unused module; a panel there would be empty until payroll is
actually run, and an empty panel trains people to ignore that part of the
screen.

## Verifying a change

```bash
./start-local.sh upgrade xn_hr_dashboard
./start-local.sh start
```

Then hard-refresh the browser: asset bundles are cached, and template and JS
changes will not appear otherwise. There are no tests in this repository, so
verification means exercising the dashboard in the UI.
