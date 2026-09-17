# Auditree Asset Register

Tracks who holds which piece of company equipment, and what condition it is in.

## Why this sits on `maintenance.equipment`

The Auditree asset master sheet is a **custody list**, not a schedule of
depreciable assets: 122 items ranging from a 250-rupee LAN cable to a
50,000-rupee laptop, tracked by holder, handover date and physical condition.

Core `maintenance.equipment` already carries almost every column of that sheet:

| Master sheet column | Field |
|---|---|
| Asset type | `category_id` |
| Brand | `model` |
| Purchase Date | `effective_date` |
| Amount | `cost` |
| Assigned to | `employee_id` + `equipment_assign_to` (from `hr_maintenance`) |
| Date of Assigning | `assign_date` |
| Inventory at Kochi | `equipment_assign_to = 'other'` + `location` |
| Comments | `note` + chatter |
| Asset ID | `xn_asset_code` -- added here |
| Condition | `xn_condition` -- added here |

`hr_maintenance` is an `auto_install` bridge, so depending on it pulls in
`maintenance` and gives every employee an Equipment smart button for free.

### Why not `om_account_asset`

That module exists to post depreciation journal entries. A 309-rupee mouse has
no business having a depreciation board. The accounting treatment of these
items is a separate exercise, and the two sides reconcile through the asset
code -- which is why that field is here rather than overloading `serial_no`.

Note that the database currently has **two** modules defining
`account.asset.asset` (`om_account_asset` and `base_accounting_kit`), with
duplicate "Assets" menus. Nothing has been posted through either. That needs
untangling before any accounting work starts; it does not affect this module.

## What it adds

**Asset Code** (`xn_asset_code`) -- the `AT-LT-002` style tag the master sheet
is keyed on. Unique, indexed, and folded into the equipment search box, so
typing a tag finds the item. Trimmed on write, because spreadsheet imports
arrive with trailing spaces often enough that `AT-LT-002` and `AT-LT-002 `
would otherwise both be accepted as distinct codes.

Deliberately separate from `serial_no`: that is the manufacturer's identifier,
this is ours.

**Condition** (`xn_condition`) -- Very Good / Good / Average / Bad / Not
Working, matching the values already in the sheet. No default: a blank means
nobody has recorded one, which is true of a few rows. Defaulting to `good`
would turn that gap into a claim, and would silently relabel a broken item as
working on any import where the column is empty.

Two search filters come with it: **Needs Attention** (bad or not working) and
**Condition Not Recorded**.

**Assigned On / Scrap Date** -- core hides both behind developer mode
(`groups="base.group_no_one"`). A handover date is the entire point of a
custody register, and the scrap date is how a written-off item stops counting
as held, so both are unhidden here.

## Who can see it

Installing core `maintenance` puts a Maintenance app in front of **every**
internal user. Two separate causes:

* its root menu carries no `groups` at all, and
* every child menu lists `base.group_user` alongside `group_equipment_manager`,
  and menu visibility is a union, so Internal User wins.

On top of that, `hr_maintenance` grants `maintenance.group_equipment_manager`
to `hr.group_hr_user` through `implied_ids`, so every HR Officer silently
becomes an Equipment Manager.

`security/xn_asset_register_security.xml` closes both:

* a new **Asset Register Manager** group, which implies Equipment Manager,
* every Maintenance menu regated on it with `(6, 0, [...])` -- replacing the
  group list rather than adding to it, which is what strips `base.group_user`,
* the `hr.group_hr_user` implication removed with `(3, ref(...))`.

Removing an implication does not walk back the memberships Odoo already
materialised, so `post_init_hook` strips Equipment Manager from users who do
not hold Asset Register Manager. It never touches the superuser, and never
touches anyone who holds the new group.

**The group ships empty apart from the administrator.** That is deliberate --
membership is assigned by hand so it cannot grow as a side effect of somebody
being given an HR role. It also means that after installing, somebody has to
grant it, or nobody can reach the register.

## The Overview dashboard

Clicking **Maintenance** opens an asset overview rather than the vendor's
maintenance dashboard. Odoo opens an app's first child menu, so the menu sits
at `sequence="-10"` against core's `0`; the vendor entry stays underneath
rather than being removed.

Panels: headline tiles, a condition donut, value by category, purchases per
year, an age-of-fleet band chart, the custody split with inventory locations,
the ten largest holders, and a row of chips for anything needing a decision.
A toggle switches the category and year charts between counts and value.
Every figure is clickable and opens the equipment list filtered to exactly the
rows behind it.

### No Chart.js

Same reasoning as `xn_hr_dashboard`: Odoo 17 ships Chart.js only in
`web.chartjs_lib`, which no backend bundle includes, so a canvas drawn without
an explicit `loadBundle` stays blank with nothing in the console. Every chart
here is a CSS box or a hand-built SVG, which cannot fail that way. Note that
this contradicts CLAUDE.md section 5, which recommends the `loadBundle` route
and cites a filename that does not exist -- the two in-house dashboards both
avoid the library outright.

### Arithmetic lives in one place

The Python endpoint returns finished figures and the component's `shape()`
turns them into percentages. The template contains no maths at all, so what is
drawn and what is counted cannot drift apart.

`xn_asset_dashboard_data` re-checks the group rather than trusting the menu: a
menu is a hint about what to show, not an access control. It also reads with
`sudo()` on purpose -- the dashboard reports the whole register, and record
rules would otherwise hand an ordinary user a total assembled from the
equipment they happen to follow, which looks like a company total and is not.

## Not included, pending a decision

SIM cards (4 rows, holding a phone number and provider) have no home here yet.
Whether they belong in Odoo at all is an open question, and adding two fields
that nothing fills is worse than leaving them out.

## Notes for whoever maintains this

* Every view xpath anchors on a **field name**, never a position.
  `hr_maintenance` replaces `owner_user_id` with `employee_id` in the form,
  tree and kanban, so a positional anchor would land somewhere different
  depending on load order.
* The unique constraint is company-wide, not per-company. Auditree runs a
  single company and the sheet's codes are unique across the whole estate.
  Postgres permits repeated NULLs, so untagged items are unaffected.
* Field tracking is deferred to `cr.precommit` callbacks in Odoo 16+. A test
  that only calls `env.flush_all()` will see no chatter message and look like
  tracking is broken. Call `env.cr.precommit.run()`, which is what a real
  request does at commit time.

## Verified

Installed against `AUDITREE_LIVE_NEW` on 2026-09-16 (`-i
maintenance,xn_asset_register`): exit 0, `Modules loaded.`, `Registry loaded`,
no new errors. 186 modules before, 190 after.

Checked in `odoo-bin shell`, all rolled back: asset code trimmed on create;
duplicate rejected; whitespace-only variant rejected as a duplicate;
all-whitespace code normalised to empty; several untagged items coexist;
condition change written to the chatter with old and new values; lookup by
asset code case-insensitive.

**Not verified:** the form, tree and search views have not been exercised in a
browser. They parse and load, which is what a clean `-i` proves, but that is
not the same as looking right.
