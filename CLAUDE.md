# CLAUDE.md — Auditree ERP Agent Guide

**Read this before making any change to this repository.**

This file is the contract every AI agent (Claude Code, Cursor, Copilot, etc.) follows when
working in this repo. It documents what the repo actually is, the traps that will bite you,
and the workflow for a safe change. Facts here were verified against the tree on
2026-08-20 — if something contradicts what you observe, trust the tree and fix this file.

---

## 1. What this repository is

**Auditree ERP** is a customized **Odoo 17.0 Community Edition** deployment for HR, payroll,
recruitment, and accounting.

The critical thing to understand: **this repo does not contain Odoo.** It contains *only*
the custom/vendor addons layer plus sanitized config templates. Everything else on disk is
gitignored working material.

Only **5 files outside `custom/addons/`** are tracked by git:

```
.gitignore
README.md
SUGGESTIONS.md
auditreelive-server.conf.example
odoo.conf.example
```

Everything else at the repo root — `start-local.sh`, `local-dev.conf`, `deploy/`,
`gcp-hosting-plan.md`, the `.tar.gz` archives, the `.dump`, the logs — is **untracked**.
Some of it is gitignored; some of it is not (see §3.2 — this matters).

### Stack

| Thing | Value |
|---|---|
| Odoo | 17.0 Community Edition (`auditreelive-server/odoo/release.py` → `version_info = (17, 0, 0, FINAL, 0, '')`) |
| Python | 3.10 (`venv/lib/python3.10`); some `.pyc` artifacts from 3.12 also exist |
| Database | PostgreSQL, DB name `AUDITREE_LIVE_NEW` |
| Local URL | http://localhost:8069 |
| Production | GCP VM `auditreelive-prod-mum` (`asia-south1-a` / Mumbai, project `auditree-prod`), systemd unit `odoo`, port 8001 behind Nginx, `workers = 2` + gevent on 8072. Served at https://odoo.auditree.com (`8.234.100.82`). Migrated from `us-central1-a` on 2026-09-17; the old VM `auditreelive-prod` is TERMINATED but retained as rollback. Staff kept working on the legacy DigitalOcean server until 2026-09-25, when its data was migrated onto GCP (`deploy/migrate_do_to_gcp.sh`) and Auditree's Odoo on DO was stopped. The DO box (`auditreeerpsvr`) is shared with other clients' Odoo instances -- never touch anything but `auditreelive` there. |
| Modules loaded | 186 at last successful boot (2026-09-05) |

---

## 2. Directory map

```
Auditree/
├── custom/addons/          ← THE TRACKED CODE. 57 modules. All real work happens here.
├── auditreelive-server/    ← Odoo 17 core source (~2 GB). GITIGNORED. Do not edit.
├── venv/                   ← Python 3.10 virtualenv. GITIGNORED.
├── deploy/                 ← GCP provisioning scripts + deploy/secrets/prod.env + 680 MB
│                             of tarballs. GITIGNORED. Contains real secrets.
├── start-local.sh          ← Local dev lifecycle script (untracked, NOT gitignored)
├── local-dev.conf          ← Local Odoo config w/ plaintext DB password (untracked,
│                             NOT gitignored)
├── odoo.conf.example       ← Sanitized template (tracked)
├── auditreelive-server.conf.example  ← Sanitized prod template (tracked)
├── README.md               ← Business-facing: what's installed, what isn't, roadmap
├── SUGGESTIONS.md          ← 25-item prioritized improvement backlog. Read before
│                             "improving" anything — it's probably already listed.
├── odoo-local.log          ← Local runtime log (gitignored)
├── *.tar.gz, *.dump        ← Multi-hundred-MB backups. Never read, move, or open these.
└── gcp-hosting-plan.md, switch-to-web-responsive-plan.md  ← Planning docs (untracked)
```

### The addons layer: three tiers

`custom/addons/` holds 57 modules. Treat them differently depending on tier:

**Tier 1 — In-house (`xn_*`), owned by this project. Edit freely.**

| Module | Purpose |
|---|---|
| `xn_auditree_erp` | Main custom module: HR employee/applicant/department/payslip/project extensions, probation crons, custom reports |
| `xn_user_custom` | Adds `is_freelancer` to `res.users`. `xn_auditree_erp` depends on it. (SUGGESTIONS #15 proposes merging the two.) |
| `xn_hr_leave_report` | Leave balance reporting — the wide-format SQL view and the year/month extension. **Active development area** (current branch: `feature/leave-report-period-filters`). |
| `xn_hr_dashboard` | Organisation panels for the HR dashboard, plus overrides that fix the vendor's department donut, birthday, event and announcement queries. Extends `hrms_dashboard` (Tier 2) without editing it — see its own README.md. Shared mailboxes (hr@, accounts@, it@, admin@) carry `employee_type = 'system'` (added by `xn_auditree_erp`); every org-wide count goes through `_xn_people_domain()` / `_xn_people_sql()` to exclude them -- use those for any new panel. |
| `xn_it_helpdesk` | IT Helpdesk app (added 2026-10-15, not yet installed anywhere). Extends OCA `helpdesk_mgmt` (Tier 3, vendored untouched from OCA/helpdesk 17.0 @ `14220ae`). Requesters = group `group_xn_helpdesk_requester` ("Raise IT Tickets"; every helpdesk_mgmt group implies it; prod trial seeds Junaid + Ayesha via `TRIAL_REQUESTER_LOGINS`, go-live = give it to all employees): create + read own tickets, **no write** -- Confirm/Reopen are sudo buttons that check the requester. IT = any `helpdesk_mgmt` group; admin = Helpdesk Manager. Stage logic keys off `helpdesk.ticket.stage.xn_state`, not stage names/ids. Internal notes ("Log note") are hidden from non-IT requesters (and only them -- other users' message searches are untouched) by a `mail.message` `_search` / `check_access_rule` override in `models/mail_message.py` -- core only hides notes from portal users. Assignable users must be members of the IT Support team (helpdesk_mgmt limits `user_id` to team members). Shared accounts (`employee_type = 'system'`) cannot see the app or raise tickets unless they are in a Helpdesk group -- it@auditree.com is, via `IT_TEAM_LOGINS` in its `post_init_hook`. helpdesk_mgmt's portal routes are overridden to redirect to the backend. |
| `xn_recruitment_cv` | Fills an application's empty candidate fields from the attached CV (PDF / .docx / .txt) through `xn_ai_core` (purpose `recruitment_cv`): Read CV button + a 15-minute cron over files attached in the last 2 days, idle while `xn_ai.enabled` is off. Never overwrites; differences go to the chatter. Portal no-reply senders are replaced. PDF text via PyPDF2 (no pdfminer in the venv). Added 2026-10-27, not yet installed anywhere. See its README.md. |
| `xn_recruitment` | Hiring process on core `hr_recruitment` (added 2026-10-23, not yet installed anywhere): hiring steps on stages (`hr.recruitment.stage.xn_round` -- key off it, not stage names), interview panels per job, a handover email with CV + previous-round feedback to the next round's interviewers, interviewer feedback, rejection email via the refuse reasons' template, hiring-status / daily-movement / source reports. Moving a candidate or refusing one sends real email -- archive the outgoing mail server before testing on a prod copy. See its README.md. |

**Tier 2 — Vendor modules with local patches. Edit with care; never re-download over them.**

These have been modified since the initial commit. Overwriting them with a fresh vendor
copy silently reverts real fixes:

- `hrms_dashboard` — patched twice (leave-count scalar fix, birthday-widget template fix,
  parameterized SQL in `get_attrition_rate`)
- `web_responsive` — added and configured
- `sign_oca` — added (OCA e-signature)

**Tier 3 — Untouched vendor modules (the other ~48). Do not edit.**

Cybrosys/OpenHRMS/MuK/OCA modules — `base_accounting_kit`, `ohrms_*`, `muk_web_*`,
`hr_payroll_community`, `dynamic_accounts_report`, `helpdesk_mgmt` (extended by
`xn_it_helpdesk`), etc. If one needs a behavior change,
**write a small `xn_*` module that inherits and overrides**, rather than patching vendor
code. Patching vendor code creates a permanent upgrade tax; do it only when inheritance
genuinely cannot express the fix, and say so in the commit message.

Roughly a dozen modules are on disk but **not installed** (`hr_custody`,
`hr_gratuity_settlement`, three competing property-management modules, `ohrms_core`,
`odoo_accounting_dashboard`, …). See README.md for the full installed/not-installed split.
Do not assume a module on disk is live.

---

## 3. Landmines — read every one of these

### 3.1 🚨 `git add -A` will produce a 3,500-file garbage commit

`git status` currently shows **~3,566 modified files**. Essentially all of them are
**file-mode changes only** (`100755 → 100644`), an artifact of the tree living on WSL and
being touched from Windows. `core.fileMode = true`, so git reports every one.

```
$ git diff --summary | head -3
 mode change 100755 => 100644 SUGGESTIONS.md
 mode change 100755 => 100644 custom/addons/advance_cash_flow_statements/README.rst
 mode change 100755 => 100644 custom/addons/advance_cash_flow_statements/__init__.py
```

**Rules:**
- **Never** `git add -A`, `git add .`, `git commit -a`, or `git commit -am`.
- **Always** stage explicit paths: `git add custom/addons/xn_hr_leave_report/models/foo.py`
- Before committing, run `git diff --cached --stat` and confirm the file list is exactly
  what you changed.
- Do not "fix" the mode churn (e.g. `core.fileMode=false`, or committing the modes) unless
  the user explicitly asks. It's a repo-wide decision with a 3,500-file diff attached.

### 3.2 🚨 Untracked ≠ gitignored — secrets are one careless `add` away

These files are untracked but **not** covered by `.gitignore`:

| File | Contains |
|---|---|
| `local-dev.conf` | `admin_passwd = admin`, `db_password = fowadhamza` |
| `start-local.sh` | A plaintext sudo password on line 32 |
| `fix_restrict_user_ids.sql`, `tick`, `gcp-working` | Ad-hoc working files |

Combined with §3.1, a single `git add -A` commits plaintext credentials. Never commit
these. If the user wants them tracked, sanitize into a `.example` first — that's the
existing pattern (`odoo.conf.example`, `auditreelive-server.conf.example`).

`deploy/` *is* gitignored and holds `deploy/secrets/prod.env` with real production
credentials. Never print its contents, never move it out of `deploy/`.

### 3.3 🚨 Non-ASCII characters get corrupted — write ASCII only

`custom/addons/xn_hr_leave_report/models/hr_leave_balance_report.py` and
`views/hr_leave_balance_report_views.xml` are full of literal `?` characters where
em-dashes and box-drawing separators used to be:

```python
    # ?? Casual Leave (id=7) ???????????????????????????????????????????????????
    casual_allocated = fields.Float(string='Casual ? Allocated', ...)
```

`file` reports these as plain ASCII — the Unicode was destroyed by a Windows-side write,
not merely mis-rendered. **Note that user-visible field labels are affected**
(`'Casual ? Allocated'`), so this is a real UI defect, not only cosmetic.

**Rule: write ASCII-only in source files.** Use `--` not `—`, `#---` not box-drawing, and
plain hyphens in `string=` labels. If you touch an affected line, repair it to ASCII while
you're there.

### 3.4 Windows/WSL path handling

The repo lives in WSL (`/home/fowadhamza/Projects/Auditree`) and is accessed from Windows
via `\\wsl.localhost\Ubuntu-24.04\...`. Consequences:

- Odoo itself only ever sees the **Linux** path. Every path inside a config, script, or
  manifest must be the `/home/fowadhamza/...` form.
- Use the Bash tool for anything that runs Odoo, psql, or the dev scripts.
- Some files carry CRLF line endings (e.g. `xn_hr_leave_report/models/__init__.py`).
  Match the file you're editing; don't reflow line endings across a whole file.

### 3.5 Git remote: SSH, and only reachable from inside WSL

`origin` is `git@github.com:fowadhamza/auditree-odoo.git` (this resolves SUGGESTIONS #11 --
history is no longer local-only). The SSH key lives in the WSL home directory, so a `git
push` run from the Windows side fails with `Permission denied (publickey)`. Push through
WSL instead:

```bash
wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /home/fowadhamza/Projects/Auditree && git push origin <branch>"
```

Reads, commits and staging work fine from either side; only the network operations need WSL.
Still push only when asked.

### 3.6 Large binaries at the repo root

`auditreelive-server.tar.gz` (507 MB), `AUDITREE_ADDONS.tar.gz` (166 MB),
`AUDITREE_FILESTORE.tar.gz` (30 MB), `AUDITREE_LIVE_NEW.dump` (13 MB), plus 680 MB more in
`deploy/`. Never read, extract, or relocate these. Avoid unfiltered recursive `find`/`grep`
from the repo root — scope searches to `custom/addons/`.

---

## 4. Running things locally

`start-local.sh` is the single entry point. Run it from the WSL path.

```bash
./start-local.sh start      # start Odoo on http://localhost:8069
./start-local.sh stop
./start-local.sh restart
./start-local.sh status
./start-local.sh logs       # tail -f odoo-local.log
./start-local.sh upgrade <module_name>    # stops Odoo, runs -u <module>, exits
```

`upgrade` defaults to `hr_holidays` if you omit the module name — **always pass the module
name explicitly.**

Under the hood it runs:

```bash
cd /home/fowadhamza/Projects/Auditree/auditreelive-server
python3 odoo-bin --config=/home/fowadhamza/Projects/Auditree/local-dev.conf \
  -d AUDITREE_LIVE_NEW -u <module> --stop-after-init
```

Addons path (from `local-dev.conf`):
`auditreelive-server/addons` then `custom/addons`.

### When you must run `-u`

Odoo does not hot-reload most changes. After editing:

| Changed | Action |
|---|---|
| Python model logic (methods only) | restart Odoo |
| Fields, `__manifest__.py`, XML views, security CSV, data | `./start-local.sh upgrade <module>` |
| A model's `init()` / SQL view definition | **`-u <module>` is mandatory** — `init()` only runs on module update. Editing the SQL string alone changes nothing in the DB. |
| Static assets (JS/SCSS/XML templates) | restart + hard-refresh; asset bundles are cached |

The SQL-view rule bites hardest in `xn_hr_leave_report`, where both models are `_auto = False`
and built entirely in `init()`.

### There are no tests

Zero test files exist across all custom modules (SUGGESTIONS #18). There is no test command,
no linter, no formatter, no CI. **Verification means running Odoo and exercising the feature
in the UI.** Never report a change as "working" on the strength of reading the code — say
plainly what you did and did not verify.

Boot health check: `./start-local.sh upgrade <module>` should end with
`Modules loaded.` / `Registry loaded`. The log is noisy with pre-existing vendor warnings
(`no _description`, `not overriding the create method in batch`, `unknown parameter`) —
those are baseline noise, not regressions you introduced. Compare against a prior boot
before chasing one.

---

## 5. Odoo module conventions used here

### Anatomy

```
custom/addons/<module>/
├── __init__.py              # from . import models
├── __manifest__.py          # name/version/depends/data — data order matters
├── models/
│   ├── __init__.py          # must import every model file
│   └── *.py
├── security/
│   ├── ir.model.access.csv  # required for every new model
│   └── *.xml                # groups, ir.rule
└── views/*.xml
```

### Manifest

- `'version': '17.0.x.y.z'` — always 17.0-prefixed.
- `data` list order matters: security CSV → views → menus → reports. Menus reference
  actions, so the action's view file must load first.
- A new model that isn't in `models/__init__.py` is never registered. (`lead_service.py`
  in `xn_auditree_erp` is exactly this bug — SUGGESTIONS #7/#16.)
- `post_init_hook` takes **one argument, `env`** — `def post_init_hook(env):`. The old
  Odoo 15/16 signature `(cr, registry)` is what most tutorials still show, and it fails at
  install with `TypeError: post_init_hook() missing 1 required positional argument`, after
  which the whole registry load is rolled back. `xn_asset_register/__init__.py` is the
  local reference. Installing a brand-new module needs `-i <module>`, not the
  `./start-local.sh upgrade` path, which only runs `-u`.

### Security

Every new model needs a row in `ir.model.access.csv`. Existing style
(`xn_hr_leave_report`), read-only report grants to two HR groups:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_hr_leave_balance_report_manager,hr_leave_balance_report_manager,model_hr_leave_balance_report,hr.group_hr_manager,1,0,0,0
access_hr_leave_balance_report_user,hr_leave_balance_report_user,model_hr_leave_balance_report,hr.group_hr_user,1,0,0,0
```

`model_id:id` is `model_` + the model name with dots replaced by underscores.
Report models get read-only (`1,0,0,0`). Gate menu items with `groups=` too.

### SQL-backed report models

The established pattern for both `xn_hr_leave_report` models:

```python
class HrLeaveBalanceReport(models.Model):
    _name = 'hr.leave.balance.report'
    _description = 'HR Leave Balance Report'
    _auto = False              # backed by a SQL view, no ORM table
    _order = 'employee_name'

    some_field = fields.Float(readonly=True)   # every field readonly=True

    def init(self):
        self.env.cr.execute("DROP VIEW IF EXISTS hr_leave_balance_report CASCADE")
        self.env.cr.execute(""" CREATE OR REPLACE VIEW ... """)
```

Requirements: an `id` column in the SELECT (an entity id, or `row_number() OVER (...)`);
every field `readonly=True`; tree views `create="false" edit="false" delete="false"`.

`tools.drop_view_if_exists(self._cr, '<view>')` is also used — either is fine, but be
consistent within a file.

**⚠️ Hardcoded leave-type IDs.** `hr_leave_balance_report.py` hardcodes live-database
primary keys — `7` Casual, `8` Sick, `9` Earned b/f, `12` Maternity, `13` Comp-off — into
`FILTER (WHERE holiday_status_id = 7)` clauses, with matching hardcoded column names and
labels. This is environment-coupled: the view is **wrong on any database whose leave-type
IDs differ**, silently returning zeros rather than erroring. Know this before changing leave
types, seeding a fresh DB, or reasoning about why the report looks empty. Don't rip it out
mid-task — flag it and keep to the task at hand.

### SQL safety

Never interpolate user or record data into SQL strings. `get_attrition_rate` in
`hrms_dashboard` was already fixed once for this (commit `71884f3`). Use parameterized
queries: `self.env.cr.execute(query, (param,))`.

A second instance of the same pattern still exists in `get_upcoming` in the same file
(the announcement `WHERE` clause). `xn_hr_dashboard` overrides that method with a
parameterized version rather than patching the vendor.

### Client-side assets: two traps

**Chart.js is not loaded in the backend.** Odoo 17 ships it only in the
`web.chartjs_lib` bundle, which no backend bundle includes — the graph view pulls it in
on demand. A `new Chart(...)` in your own OWL code silently does nothing unless you
`await loadBundle("web.chartjs_lib")` first (`@web/core/assets`). There is no error; the
canvas just stays blank. `xn_hr_dashboard/static/src/js/xn_dashboard.js` shows the pattern.

**XML comments cannot contain `--`.** `<!-- Today ------- -->` is not well-formed XML and
kills the whole asset bundle. This bites because `# ----` separators are fine in the
Python files right next to them.

**Anchor template xpaths by class, never by position.** `//div[1]` matches every div that
is the first div child of its parent, so a second `<xpath>` in the same `t-inherit` block
will target the node the first one just inserted. Use `//div[hasclass('the-class')]`.
`position="replace"` with an empty body deletes a node, which is the only way to remove
vendor markup — `t-inherit` in extension mode otherwise only adds.

### Python style in `xn_*` modules

```python
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)
```

4-space indent, `_logger` over `print()` (SUGGESTIONS #5 tracks the leftovers),
docstrings on non-obvious methods, `_description` on every model.

Match the surrounding file's conventions. Vendor code is often inconsistent with this — when
editing vendor code, follow the file you're in, not this section.

### XML views

`<?xml version="1.0" encoding="utf-8"?>` then `<odoo>`. IDs follow
`view_<model>_<type>`, `action_<name>`, `menu_<name>`. Escape operators in domains
(`&lt;`, `&gt;`). Use `optional="show"` on wide report trees and `column_invisible="1"`
for fields needed only by search domains.

---

## 6. Workflow for a change

1. **Read `SUGGESTIONS.md` first.** 25 known issues are catalogued there with file and line
   references. If your task overlaps one, you now have the context — and if you're about to
   "helpfully" fix something adjacent, check whether it's a listed item the user has
   deliberately deferred.
2. **Identify the tier** (§2). In-house → edit. Vendor-patched → careful. Untouched vendor
   → prefer a new `xn_*` module that inherits.
3. **Work on a branch.** Current branches: `main`, `feature/leave-report-period-filters`
   (active), `feature-gcp-deployment`, `feature/readme-and-roadmap`,
   `fix-employee-dashboard-balance`.
4. **Make the change**, ASCII-only (§3.3), matching local conventions (§5).
5. **Upgrade and boot**: `./start-local.sh upgrade <module>`, then `start`, then check the
   log for genuinely new errors.
6. **Verify in the UI** — there are no tests to lean on.
7. **Stage explicitly** (§3.1). Confirm with `git diff --cached --stat`.
8. **Commit** in the existing style: `type(scope): summary`, e.g.
   `fix(xn_hr_leave_report): correct menus XML - add Leave Balance Report menu`.
   Commit only when the user asks.
9. **After a prod deploy**, move `main` to the deployed commit and tag it (§8 "`main` =
   what is live on prod").

### Never do these without an explicit request

- `git add -A` / `git commit -a` / `git commit -am` (§3.1)
- Commit `local-dev.conf`, `start-local.sh`, or anything from `deploy/`
- Edit anything in `auditreelive-server/` — it's untracked stock Odoo source
- Edit `venv/`
- Touch the `.tar.gz` / `.dump` archives
- Drop, restore, or migrate the `AUDITREE_LIVE_NEW` database
- Run anything against production (`gcloud compute ssh`, the `deploy/*.sh` scripts)
- Add a git remote or push
- Reformat / re-lint files wholesale — the mode churn already makes diffs hard to read
- Bulk-fix items from `SUGGESTIONS.md` that weren't asked for

---

## 7. Known issues you will trip over

Full detail in `SUGGESTIONS.md`; the ones that most often confuse an agent mid-task:

| Thing you'll notice | Status |
|---|---|
| `security/secutity.xml` misspelled in `xn_auditree_erp` | Known (#12). Works because the manifest matches the typo. Renaming means updating the manifest too. |
| `class LeadService(models.Model): _inherit = "project.project"` | Known (#9) — misnamed class, not a bug. |
| `lead_service.py` not imported in `models/__init__.py` | Known (#7/#16) — dead code. |
| Unscoped `sudo().search([])` in employee crons | Known (#8) — multi-company leak. |
| `_compute_hide_revert_back` sends email from a compute method | Known (#6) — real bug, deliberate backlog item. |
| Probation thresholds hardcoded as 75/80/90 days | Known (#20). |
| `adhar_pan_uniq` says "per company" but isn't company-scoped | Known (#4). |
| Log full of `no _description` / `not overriding create in batch` warnings | Baseline vendor noise, not your regression. |
| `admin_passwd = admin` in `local-dev.conf` | Known (#1). Local dev only — production uses `deploy/secrets/prod.env`. |
| Old pinned deps with CVEs in `auditreelive-server/requirements.txt` | Known (#2). |

Encountering one of these is not a signal to fix it. Mention it if it's in your path;
otherwise stay on task.

---

## 8. Production

Production config is generated by `deploy/06_prod_config_systemd.sh` from
`deploy/secrets/prod.env` — it is not a file you edit directly. Prod runs `proxy_mode = True`
behind Nginx, port 8001, systemd unit `odoo`, user `auditreelive`,
addons at `/opt/odoo17/auditreelive/custom/addons`.

Production is served at **https://odoo.auditree.com**, which points at the static IP
`auditreelive-ip` (`34.63.212.242`). Nginx terminates TLS with a certbot-managed Let's
Encrypt certificate and 301-redirects port 80 to 443; renewal is automatic and working.
`web.base.url` is `https://odoo.auditree.com`. A request to the raw IP returns a stock
nginx 404 -- nginx matches on `server_name`, so always test with the hostname, never the
IP. `erp.auditree.com` is a *different*, unrelated DigitalOcean box serving a static page.

The config lives at **`/etc/auditreelive-server.conf`** — not `/etc/odoo/odoo.conf`. Take the
invocation from the unit rather than reconstructing it (`systemctl cat odoo`):

```
User=auditreelive
ExecStart=/opt/odoo17/auditreelive/venv/bin/python \
          /opt/odoo17/auditreelive/auditreelive-server/odoo-bin \
          --config=/etc/auditreelive-server.conf
```

The addons tree is owned by `auditreelive` and is not world-readable, so even `grep` and `ls`
against it need `sudo` from an SSH login.

Deployment is a set of manual, numbered shell scripts in `deploy/` (`04b_deploy_code_fresh.sh`,
`05_restore_db_filestore.sh`, `06_prod_config_systemd.sh`, `07_nginx_http_only.sh`) driven by
`gcloud`. There is no CI/CD. **Do not run any of these.** Deployment is a human decision.

`list_db = False` **is** applied on the live box (verified against
`/etc/auditreelive-server.conf` on 2026-09-19), resolving SUGGESTIONS #21. `log_level = warn`
is still absent from the live config (#22 stands) though `06_prod_config_systemd.sh`
generates it. Backups, verified 2026-09-28:
- **Daily disk snapshots** of the boot disk `auditreelive-prod-boot` (the disk name differs
  from the VM name) via resource policy `auditree-daily-30d`: 19:00 UTC window, kept **30 days**
  (the older 14-day policy `auditree-daily` is detached but kept so its snapshots expire).
  Whole-disk and crash-consistent -- they restore the entire server, not single records.
- **Nightly `pg_dump` + filestore** (since 2026-09-28): `/opt/auditree-backup/auditree_backup.sh`
  (source: `deploy/auditree_backup.sh`), cron `/etc/cron.d/auditree-backup` at 20:30 UTC /
  02:00 IST, log `/var/log/auditree-backup.log`, status line in
  `/var/backups/auditree/last_status` (`OK` / `OK_LOCAL_ONLY` / `FAILED`). Keeps 7 days on the
  VM and uploads to `gs://auditree-prod-backups/daily/<date>/` (+ `monthly/` on the 1st);
  bucket lifecycle deletes `daily/` after 31 days and `monthly/` after 366.
  `deploy/verify_backup.sh <dir>` restore-tests a set locally. ~385 attachments reference
  files that were already missing on the source (stock payment/badge images inherited from
  DO) -- recorded as `missing_in_source` in each `info.txt`, not a backup fault.
- Since 2026-09-28 the VM runs as `auditree-vm@auditree-prod.iam.gserviceaccount.com`, scope
  `cloud-platform` (was the default compute account, which holds project Editor). Roles:
  logWriter, metricWriter, and on the bucket only `storage.objectCreator` + `objectViewer` --
  it can add and read backups but **not delete or overwrite** them (verified). `objectViewer`
  is required: `gcloud storage cp` reads the destination first and fails 403 without it.
  Because objects cannot be overwritten, backup folders are `<date>_<HHMM>` UTC. Changing the
  VM's service account needs a VM stop; nginx answers 502 for the ~20 s Odoo takes to boot.
- Do not probe the gevent port (8072) with page requests: it only serves `/websocket`, and a
  plain `GET /web/login` there logs a `KeyError: 'REQUEST_URI'` traceback that is not a fault.
- **Manual `pg_dump` + filestore sets** in `gs://auditree-prod-backups/` (asia-south1,
  versioning on, no lifecycle): `2026-09-17/`, `2026-09-17-premove/`,
  `20260925_052504-pre-do-migration/`, plus the nightly `daily/` and `monthly/` sets.
- Everything sits in one project whose only Owner is a personal Gmail account.

### 🚨 Raising `workers` moves the websocket to a different port

Odoo serves the websocket/bus on `http_port` **only** in threaded mode (`workers = 0`). Set
`workers > 0` and the bus moves to a dedicated gevent worker on `gevent_port`. nginx's
`location /websocket` must follow it, or live chat, notifications and the bus break
**silently** -- no error in the log, the UI just stops updating.

`06_prod_config_systemd.sh` generates `workers = 2` + `gevent_port = 8072`, and
`07_nginx_http_only.sh` points `/websocket` at 8072 to match. Change one and you must change
the other. **This is now the live state**: verified 2026-09-19, `/etc/auditreelive-server.conf`
has `workers = 2` / `gevent_port = 8072` and `pgrep -af odoo-bin` shows the worker set plus an
`odoo-bin gevent` process. Do not assume threaded mode when reasoning about prod.

### 🚨 An `odoo shell` write does not reach the running workers

Editing a record through `odoo-bin shell` commits to the database, but the **already-running**
server processes keep serving from their in-process caches. A QWeb/`ir.ui.view` edit made this
way lands in the DB and the site still renders the old markup -- with no error anywhere. An
HTTP request calls `registry.signal_changes()` at the end of the request; `odoo shell` never
does, so the `base_cache_signaling_*` sequences are never bumped and the other processes have
nothing to detect.

Hit on 2026-09-19 fixing the `/contactus` address. Finish any shell-side data change with:

```python
env.registry.clear_cache('templates', 'assets', 'default')
env.registry.signal_changes()
```

Each worker then picks it up in `check_signaling()` on its next request -- no `systemctl
restart` and no downtime. With `workers = 2` there are several processes to reach, so the
symptom is easy to misread as "the write failed". Verify by fetching the real URL, not by
re-reading the DB: the DB will look correct either way.

### 🚨 Never create a prod database whose name starts with `AUDITREE_LIVE_NEW`

Prod has `dbfilter = AUDITREE_LIVE_NEW` and no `db_name`. Odoo applies the filter with
`re.match` (`odoo/http.py`), which anchors only at the start, and lists every database owned
by `auditreelive`. A second database such as `AUDITREE_LIVE_NEW_backup` therefore also
matches, Odoo loses its single-database mode, and **every request 303-redirects to
`/web/database/selector`** -- which `list_db = False` then refuses. The site is down with no
error in the log. Hit on 2026-09-25 during the DO migration (caught by its health check and
rolled back). Name backups with a different prefix -- `bak_pre_do_<ts>_AUDITREE_LIVE_NEW` is
the convention -- or anchor the filter (`^AUDITREE_LIVE_NEW$`). Locally this never shows,
because local runs pass an anchored `--db-filter` or a single `-d`.

### 🚨 The venv's `zope.*` packages are invisible to `pkg_resources`

Hit on 2026-09-17 when `workers` was first raised above 0. The gevent worker crash-looped
silently -- nothing in the Odoo log, because it died inside `gevent.monkey.patch_all()` before
logging existed. The real error only appears in `journalctl -u odoo`:

```
pkg_resources.DistributionNotFound: The 'zope.event' distribution was not found
and is required by the application
```

`zope.event` and `zope.interface` were not in the venv at all. `importlib.metadata` and `pip`
both reported them present because they leak in from the system Python, so
`pip install zope.event` answers "Requirement already satisfied" and changes nothing.
`pkg_resources` -- which gevent's entry-point hook uses -- correctly refused to resolve them.

Fixed with `--ignore-installed`, pinned to the era of the rest of the stack:

```bash
sudo -u auditreelive /opt/odoo17/auditreelive/venv/bin/pip install   --no-deps --ignore-installed 'zope.event==4.6' 'zope.interface==5.5.2'
```

Two lessons: **a gevent worker that dies leaves no trace in the Odoo log -- check
`journalctl -u odoo`**, and **"Requirement already satisfied" does not mean the package is in
this venv.** Verify with `ls venv/lib/python3.10/site-packages/<pkg>*`, not with pip.

### 🚨 `07_nginx_http_only.sh` would strip TLS off the live server

That script writes an HTTP-only vhost; certbot then rewrites it in place to add `listen 443`,
the cert paths and the 80->443 redirect. Re-running it on the live box would therefore undo
TLS. It now checks for an existing `ssl_certificate` and refuses unless you pass
`FORCE_OVERWRITE_TLS=1`, after which you must immediately re-run
`sudo certbot --nginx -d odoo.auditree.com`.

### What `04b_deploy_code_fresh.sh` actually does

Know these before anyone runs it:

- It tars **the live working checkout**, not a git commit. Uncommitted and untracked files
  ship; committed work on a branch you haven't checked out does not. `git status` is the
  real manifest.
- On the VM it does `sudo rm -rf` of `auditreelive-server`, `custom` **and `venv`**, then
  untars and rebuilds the venv from `requirements.txt`.
- **It never restarts Odoo.** Between the script finishing and a manual restart, the running
  process is serving from deleted inodes -- up, but executing code that no longer exists on
  disk. A restart is required to finish the deploy, not optional.
- A QWeb/view/field change also needs `-u <module>` against `AUDITREE_LIVE_NEW` on the VM;
  copying files alone changes nothing the users see.
- The venv rebuild had an unpinned `pip install pandas` that resolved numpy to 2.x, which is
  binary-incompatible with pandas 1.5.3 and broke the venv (`ValueError: numpy.dtype size
  changed`). Pinned 2026-09-10. If a deploy ever leaves Odoo unable to boot, check
  `venv/bin/python -c "import pandas"` before anything else.

Sequence that works: run the script, verify `import pandas` on the VM, `systemctl stop odoo`,
run `-u <module> --stop-after-init`, `systemctl start odoo`, confirm `is-active`.

### 🚨 A prod `-u` prints nothing to stdout

The prod config sets `logfile = /var/log/auditreelive/auditreelive-server.log`, so
`odoo-bin -u <module> --stop-after-init` writes **nothing** to stdout. Locally it writes
everything, which is what makes this a trap.

Do not gate anything on stdout. A wrapper that checks `grep "Modules loaded."` against the
captured stdout sees an empty string, concludes the upgrade failed, and -- if it has a
rollback path -- reverts working code on top of an already-upgraded database. That happened
on 2026-09-14 and left prod with the DB at the new version and the code at the old one.

Verify a prod upgrade by **exit code** plus the real logfile, reading only lines added since
you started:

```bash
MARK=$(sudo wc -l < /var/log/auditreelive/auditreelive-server.log)
# ... run the -u ...
sudo tail -n +$((MARK + 1)) /var/log/auditreelive/auditreelive-server.log \
  | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded"
```

### `main` = what is live on prod

`main` tracks the code running on odoo.auditree.com -- nothing more, nothing less. Feature
work lives on branches until it is deployed. Each deploy is tagged `prod-YYYY-MM-DD[b|c|d]`;
the latest tag is the prod state (as of 2026-10-23: `prod-2026-10-20` = `bdd1838`). The
fingerprint check on 2026-10-19 found one gap: 4 `xn_hr_dashboard` files on prod that match
no commit (listed in the `prod-2026-10-19` tag message).

**`sh_backend_base` is deployed but not in git** (licence). It is gitignored since commit
"chore: stop tracking sh_backend_base"; older history still contains it. Two traps:
- Pulling that commit into a working tree where the module was tracked **deletes it from
  disk**. Put it back right away (it stays untracked and ignored):
  `git restore --source=<commit>~1 --worktree custom/addons/sh_backend_base`
- `04b` does `rm -rf custom` on the VM and ships the working tree. If the module is
  missing locally, **the deploy removes an installed module from prod** and Odoo fails to
  load. Check `ls custom/addons/sh_backend_base/__manifest__.py` before any `04b` run.
GitHub history was rewritten once (2026-10-18) to purge it; a machine restored from an
older backup merged the old history straight back. Do not try another purge unless every
clone is re-synced first.

Rules:
- **Deploy only committed code.** `04b` and the one-module tar both copy the working tree,
  so commit first and ship from a clean checkout of that commit. Deploying uncommitted
  files is how prod drifted from every commit in Sept 2026.
- **After the deploy, fast-forward `main` and tag it** (from WSL):
  ```bash
  git fetch . $(git rev-parse <deployed-commit>):refs/heads/main   # fast-forward only;
                                            # needs the FULL sha -- a short id fails
  git tag -a prod-YYYY-MM-DD <deployed-commit> -m "what was deployed"
  git push origin main prod-YYYY-MM-DD
  ```
- If a deploy contains several branches, merge them into one branch first and deploy that.

**Checking what prod actually runs.** Per-module fingerprint on the VM (read-only):

```bash
cd /opt/odoo17/auditreelive/custom/addons && sudo LC_ALL=C bash -c 'for m in */; do m=${m%/}
  echo "$m $(cd "$m" && find . -type f ! -path "*/__pycache__/*" ! -name "*.pyc" -print0 \
    | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-12)"; done'
```

Two traps when comparing those hashes from the Windows side: Git for Windows sets
`core.autocrlf=true` system-wide, so `git archive` / checkout rewrite line endings (pass
`-c core.autocrlf=false`), and its `sha256sum` prints `hash *./file` (binary marker) where
Linux prints `hash  ./file`. Separately, many files in the WSL working tree carry CRLF while
git stores LF, and deploys ship the working tree -- so prod files are often CRLF and never
byte-match a commit. Compare with CRs stripped, or against the working tree.

### Shipping one module instead of the whole tree

`04b` uploads ~670 MB (2.0 GB core + 238 MB custom) and rebuilds the venv. For a change
confined to `custom/addons/`, none of that is needed, and the venv rebuild is the step that
has actually broken prod. Ship just the module:

```bash
tar czf x.tar.gz -C custom/addons --exclude=__pycache__ --exclude='*.pyc' <module>
gcloud compute scp x.tar.gz auditreelive-prod-mum:/tmp/ --tunnel-through-iap \
  --project=auditree-prod --zone=asia-south1-a
# on the VM: back the module up OUTSIDE custom/addons (Odoo scans that directory),
# untar, chown -R auditreelive:auditreelive, then stop / -u / start.
```

Used for `xn_hr_dashboard` on 2026-09-14: 37 KB uploaded, core and venv untouched.

### SSH access to the VM

`allow-ssh-restricted` allowlists a handful of `/32`s plus `35.235.240.0/20` (IAP);
`default-allow-ssh` is disabled. A rotated home IP shows up as `Connection timed out` on
port 22 -- not an auth error. Either add the current IP to the rule's `--source-ranges`
(which *replaces* the list, so repeat every existing entry) or add `--tunnel-through-iap`
to the `scp`/`ssh` calls in the deploy script, which works from any network.

---

## 9. Keeping this file honest

If you discover something an agent would need to know before changing code — a new landmine,
a convention, a corrected fact — update this file in the same change. If a claim here turns
out to be stale, fix it rather than working around it.

Companion docs: **`README.md`** (business view: what's installed, what isn't, roadmap) and
**`SUGGESTIONS.md`** (prioritized technical backlog with file/line references).
