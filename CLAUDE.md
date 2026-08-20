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
| Production | GCP VM `auditreelive-prod` (`us-central1-a`, project `auditree-prod`), systemd unit `odoo`, port 8001 behind Nginx. A legacy DigitalOcean server also exists. |
| Modules loaded | 182 at last successful boot |

---

## 2. Directory map

```
Auditree/
├── custom/addons/          ← THE TRACKED CODE. 53 modules. All real work happens here.
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

`custom/addons/` holds 53 modules. Treat them differently depending on tier:

**Tier 1 — In-house (`xn_*`), owned by this project. Edit freely.**

| Module | Purpose |
|---|---|
| `xn_auditree_erp` | Main custom module: HR employee/applicant/department/payslip/project extensions, probation crons, custom reports |
| `xn_user_custom` | Adds `is_freelancer` to `res.users`. `xn_auditree_erp` depends on it. (SUGGESTIONS #15 proposes merging the two.) |
| `xn_hr_leave_report` | Leave balance reporting — the wide-format SQL view and the year/month extension. **Active development area** (current branch: `feature/leave-report-period-filters`). |

**Tier 2 — Vendor modules with local patches. Edit with care; never re-download over them.**

These have been modified since the initial commit. Overwriting them with a fresh vendor
copy silently reverts real fixes:

- `hrms_dashboard` — patched twice (leave-count scalar fix, birthday-widget template fix,
  parameterized SQL in `get_attrition_rate`)
- `web_responsive` — added and configured
- `sign_oca` — added (OCA e-signature)

**Tier 3 — Untouched vendor modules (the other ~48). Do not edit.**

Cybrosys/OpenHRMS/MuK/OCA modules — `base_accounting_kit`, `ohrms_*`, `muk_web_*`,
`hr_payroll_community`, `dynamic_accounts_report`, etc. If one needs a behavior change,
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

### 3.5 No git remote

`git remote -v` is empty. All history is local-only. This is SUGGESTIONS #11 and the
single largest operational risk in the repo. Do not assume `git push` exists, and do not
add a remote without being asked.

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

Deployment is a set of manual, numbered shell scripts in `deploy/` (`04b_deploy_code_fresh.sh`,
`05_restore_db_filestore.sh`, `06_prod_config_systemd.sh`, `07_nginx_http_only.sh`) driven by
`gcloud`. There is no CI/CD. **Do not run any of these.** Deployment is a human decision.

Production still lacks `list_db = False`, `log_level = warn`, and automated backups
(SUGGESTIONS #21, #22, #24).

---

## 9. Keeping this file honest

If you discover something an agent would need to know before changing code — a new landmine,
a convention, a corrected fact — update this file in the same change. If a claim here turns
out to be stale, fix it rather than working around it.

Companion docs: **`README.md`** (business view: what's installed, what isn't, roadmap) and
**`SUGGESTIONS.md`** (prioritized technical backlog with file/line references).
