# Odoo 17 -> 18 Migration: Status and Resume Guide

**Branch:** `experiment/odoo-18-upgrade` (based on `main` @ `33b940a`)
**Last worked:** 2026-08-29
**Status:** Migration proven end to end. Four blockers outstanding. Not ready to cut over.

Read this before resuming. It records state that exists outside git and will
not be obvious from the diff.

---

## 1. Bottom line

The hard part works. OpenUpgrade migrated the schema on the first attempt with
zero critical errors, all business data survived intact, and 185 of 187 modules
upgrade cleanly. Nothing found suggests this migration is infeasible.

What remains is four blockers (one vendor bug, two purchases, one design
decision) and the manual UI verification, which has **not been started**.

**Deadline:** Odoo supports the three most recent versions. Odoo 20 is expected
around September-October 2026; when it ships, Odoo 17 leaves the support window.

---

## 2. Test environment (all outside the repo)

Everything lives in `~/Projects/odoo18/`, deliberately outside `Auditree/` so a
1.3 GB tree cannot be swept into a commit (see CLAUDE.md 3.1).

```
~/Projects/odoo18/
  odoo/              Odoo 18.0.0 FINAL, shallow clone, 1.3 GB
  venv/              Python 3.12 venv (NOT the repo's 3.10 venv)
  addons18/          26 vendor 18.0 modules, fetched by sparse checkout
  _deferred18/       base_accounting_kit - broken, see section 5
  openupgrade/       OCA/OpenUpgrade 18.0
  full.conf          main config: addons18 ahead of custom/addons
  migrate.conf       core-only config used for the OpenUpgrade run
  baseline_17.dump   pg_dump of AUDITREE_LIVE_NEW, restores a clean copy in ~30s
  start18.sh         launcher - USE THIS, see gotcha in section 8
  logs/
```

| | |
|---|---|
| Odoo 17 (live) | port 8069, db `AUDITREE_LIVE_NEW` - never modified, only read |
| Odoo 18 (test) | port 8169, db `AUDITREE_18_TEST` - disposable |

`full.conf` pins `dbfilter = ^AUDITREE_18_TEST$`, so the 18 instance physically
cannot open the live database.

### Start / stop

```bash
# start (always via the script - see gotcha 8.1)
nohup ~/Projects/odoo18/start18.sh > ~/Projects/odoo18/logs/server.out 2>&1 &

# stop only the 18 instance, leaving live 17 alone
pkill -f "odoo-bin.*odoo18"

# reset the test db to a clean pre-migration copy (~30s)
dropdb -h localhost -U fowadhamza --if-exists AUDITREE_18_TEST
createdb -h localhost -U fowadhamza -E UTF8 -T template0 AUDITREE_18_TEST
pg_restore -h localhost -U fowadhamza -d AUDITREE_18_TEST -j 4 \
  ~/Projects/odoo18/baseline_17.dump
```

### Re-run the OpenUpgrade migration

```bash
cd ~/Projects/odoo18/odoo
~/Projects/odoo18/venv/bin/python odoo-bin \
  -c ~/Projects/odoo18/migrate.conf -d AUDITREE_18_TEST \
  --update all --stop-after-init --no-http \
  --load=base,web,openupgrade_framework
```
Takes about 8 minutes. Then switch to `full.conf` for normal runs.

---

## 3. Database-side fixes NOT captured in this repo

**These are the most important thing in this document.** They live only in
`AUDITREE_18_TEST` and must be re-applied to any future migration, including
production. Each fails in a way that does not point back to its cause.

**3.1 Extra Python packages** beyond Odoo's `requirements.txt`. Nothing
surfaces these until a module tries to import them:
```
pandas qifparse ofxparse openpyxl pdfminer.six phonenumbers
```
`pandas` is required by `hrms_dashboard`; `qifparse` by `base_accounting_kit`.

**3.2 XML ID remap for `equipment_request_it_operations`.** Cybrosys renamed all
four group XML IDs in 18.0 without shipping a migration script, so the module
tries to create groups that already exist and dies on the
`res_groups_name_uniq` constraint. Remap before upgrading:
```sql
UPDATE ir_model_data SET name = 'equipment_request_it_operations_group_department_manager'
  WHERE module='equipment_request_it_operations' AND name='group_equipment_department_manager';
UPDATE ir_model_data SET name = 'equipment_request_it_operations_group_hr_officer'
  WHERE module='equipment_request_it_operations' AND name='group_equipment_hr_officer';
UPDATE ir_model_data SET name = 'equipment_request_it_operations_group_stock_manager'
  WHERE module='equipment_request_it_operations' AND name='group_equipment_stock_manager';
UPDATE ir_model_data SET name = 'equipment_request_it_operations_group_admin'
  WHERE module='equipment_request_it_operations' AND name='group_equipment_admin';
```

**3.3 Two orphaned view records.** Stale Odoo 17 arch stored in the database,
containing `/tree/` xpaths. Invisible to any file-level audit: the module files
are clean, but Odoo validates stored views during upgrade and aborts. The error
names a file that does not contain the offending expression.
```sql
-- base_accounting_kit.view_invoice_asset_category (dropped in 18.0)
-- bi_crm_task.inherit_account_move_form (module archived)
DELETE FROM ir_ui_view WHERE arch_db::text LIKE '%/tree/%';
-- also delete the matching ir_model_data rows
```

**3.4 Broken website logo/favicon attachments.** They point at filestore files
that do not exist, and Odoo 18 returns HTTP 500 on `/web/login` as a result.
Odoo 17 tolerated this silently.
```sql
DELETE FROM ir_attachment
 WHERE res_model='website' AND res_field IN ('logo','favicon')
   AND store_fname IS NOT NULL;
```

**3.5 Local vendor patch.** `addons18/base_accounting_kit/views/res_config_settings_views.xml`
has one xpath commented out (the Enterprise "Budgets" upsell removal). It lives
outside git and is lost on any re-fetch from Cybrosys. Root cause never
confirmed - see 5.2.

---

## 4. What changed in this repo

Two commits:

- `e78bbc7` chore(addons): archive 18 unused modules, defer 4 pending Odoo 18 port
- `50eebd1` feat(odoo18): port in-house modules to Odoo 18

**`custom/_archive/` (18 modules)** - not installed, no port planned. Odoo 18
hard-validates manifest versions: a `17.0.x.y` string raises ValueError and
aborts the **entire** registry load, not just that module. So unused modules
blocked every boot. Includes `insafety_property_rent`, which sets
`auto_install: True` and re-queues itself whenever contacts/account/mail are
present - removing it from the addons path is the only durable fix.

**`custom/_deferred/` (4 modules)** - installed, still need work. See section 5.

**Ported to 18.0.1.0.0:** `xn_auditree_erp`, `xn_user_custom`,
`xn_hr_leave_report`, `hr_job_offer_letter`, `msr_bank_customization`,
`msr_company_header`.

**`xn_hr_leave_report` also got:** `<tree>` -> `<list>`, `view_mode` tree ->
list, and 15 corrupted field labels repaired (`Casual ? Allocated` ->
`Casual - Allocated`, same for Sick / Earned b-f / Maternity / Comp-off). Those
rendered as literal question marks in the HR UI - a pre-existing defect
(CLAUDE.md 3.3), not migration fallout.

---

## 5. The four blockers

### 5.1 `msr_company_header` - DO THIS FIRST
Odoo 18 rewrote the report layouts. Six of its ten inheritance anchors no longer
exist; the `boxed` layout lost both of its.

| Template | Anchor | Odoo 18 |
|---|---|---|
| standard | `//div[hasclass('row')]` | present |
| standard | `<div t-field="company.report_footer">` | GONE |
| bold | `//div[hasclass('row')]` | present |
| bold | `<span t-if="company.is_company_details_empty">` | GONE |
| bold | `<span t-else="" t-field="company.company_details">` | GONE |
| bold | `<span t-field="company.report_footer">` | present |
| boxed | `//div[hasclass('row')]` | GONE |
| boxed | `<div t-field="company.report_footer">` | GONE |
| striped | `<div t-field="company.report_header">` | GONE |
| striped | `<div t-field="company.report_footer">` | present |

Odoo 18 removed the company address/details blocks from the report footer
entirely and dropped the `o_clean_header` wrapper from the header.

**Why it is first:** `xn_auditree_erp` depends on it, so the main HR/payroll
customization cannot migrate until this is done. It looks cosmetic; it is not.

**Why it needs a human:** the output is customer-facing invoices. A wrong anchor
still renders, just wrong - misplaced logo, duplicated footer, missing address.
That passes a boot test and gets caught by a customer. Needs whoever owns
invoice appearance.

### 5.2 `base_accounting_kit` - report to Cybrosys
Three independent defects in their 18.0 release. Currently in `_deferred18/`.
Blocks `dynamic_accounts_report`.

1. `views/res_config_settings_views.xml` - `//setting[@id='account_budget']`
   xpath will not resolve, though the element **is** present in the stored
   parent view and nothing else removes it. Only that element carries
   `groups="account.group_account_user"`. Root cause **never confirmed**;
   worked around by commenting the xpath out.
2. `views/account_move_views.xml` - fixed, see 3.3 (stale DB views).
3. `views/multiple_invoice_form.xml` - `Field 'copy_name' does not exist` on
   `account.journal`. The model layer is sound: `multiple_invoice_ids` is
   registered as a one2many to `multiple.invoice`, the inverse `journal_id`
   exists, `copy_name` is a real column and a real `ir_model_fields` row. Odoo
   18 will not resolve it through the inline subview. Removing the `<div>`
   wrapper was tried and **did not** help.

Three independent defects in one module suggests their 18.0 release was not
tested against a real upgrade path. Worth raising with them - they can fix it
once for every customer instead of each site carrying local patches forever.

### 5.3 `bi_crm_task` - purchase
No public 18.0 source. Apps Store only ("Create Task from Lead", BrowseInfo).
This is live CRM functionality, not dead weight.

### 5.4 `query_deluxe` - purchase or drop
GitHub `main` is at 19.0.0.1; there is no 18.0 branch. Apps Store only.
**Consider dropping it:** it lets users execute arbitrary SQL and carried a
privilege-escalation CVE in 17.x before 17.0.0.4. A migration is a natural
moment to retire it.

---

## 6. Other findings worth knowing

**6.1 The live filestore is 35% incomplete.** 497 of 1,401 attachments in
`AUDITREE_LIVE_NEW` point at files that do not exist. Pre-existing, not
migration damage - but Odoo 18 is stricter and surfaces it where 17 stayed
quiet. Breakdown: 392 stock `payment.method` icons, 45 gamification badges,
16 payment-provider images, 12 onboarding images, 15 partner avatars across 3
partners, and **only 2 non-image attachments, both generated `.scss` files**.
No invoices, contracts or uploaded documents are missing.

**6.2 `xn_auth_microsoft` is installed in the DB but its code is on
`feature/microsoft-365-login`.** On this branch it shows as `to upgrade` with no
source. Not a migration issue. The Microsoft 365 provider is disabled, has no
client ID, and zero users have an OAuth identity, so nothing is configured.

**6.3 `xn_hr_leave_report` on this branch is the OLDER version.** `main` has
17.0.1.0.0; `rebuild/leave-report-clean-baseline` and
`feature/microsoft-365-login` have 17.0.3.0.0. Commit `4dbd8cd` on that branch
**removed the hardcoded leave-type IDs** that CLAUDE.md 5 flags as fragile. The
port here was applied to the older code by explicit decision - reconcile later.

**6.4 Ten allocations flipped `validate` -> `refuse` during migration.** All
belong to three departed employees (Athira MP, Ananya Saxena, Pranoti Patil)
whose allocations had already expired. Confirmed correct behaviour, not
corruption.

**6.5 Uncommitted work sits in `custom/_archive/`.** `invoice_format_editor/reports/normal_invoice_templates.xml`
has ~19 uncommitted lines adding "Invoice Number" and "Conversion Rate" columns,
related to commit `3552d79`. The module was archived because it is not
installed. The work is intact but in a directory implying it is dead. Decide
whether to keep or restore it.

**6.6 Five core modules no longer exist in Odoo 18** and were dropped during
migration: `account_payment_term`, `sale_product_configurator`,
`spreadsheet_dashboard_purchase`, `spreadsheet_dashboard_purchase_stock`,
`website_form_project`. Behaviour absorbed elsewhere. Explains any feature that
seems to have moved.

---

## 7. What has NOT been done

**No business function has been verified.** The code loads; that is all that has
been proven. Nobody has confirmed that a payslip calculates correctly, an
invoice renders right, or a leave balance is accurate. With no test suite this
is manual UI work across every module, and it is the single largest remaining
cost. Do not read "187 modules loaded" as "the migration works".

---

## 8. Gotchas

**8.1 Always launch via `start18.sh`.** Commands sent through
`wsl.exe -- bash -lc '...'` silently lose single quotes and `$VAR` / `$!`. A
`nohup` launch was mangled this way and started the server under the **system**
Python with a stale werkzeug from `~/.local/`, producing a misleading
`NameError: GEOIP_EMPTY_COUNTRY is not defined` and HTTP 500 on every page.
`start18.sh` pins `VIRTUAL_ENV`, restricts `PATH`, and clears `PYTHONPATH`.

**8.2 XML comments cannot contain `--`.** Repairing the corrupted separators
with hyphen rules broke the file with
`lxml.etree.XMLSyntaxError: Double hyphen within comment`. Use `=` runs in XML;
`#---` is fine in Python.

**8.3 Editing via the Windows path rewrites line endings.** Several files ended
up with whole-file CRLF/LF churn and had to be reverted. Check
`git diff --ignore-cr-at-eol` before committing to separate real changes from
noise.

**8.4 CLAUDE.md 3.5 is stale.** It says there is no git remote. There is:
`origin git@github.com:fowadhamza/auditree-odoo.git`, with several branches
already tracking it.

---

## 9. Resume order

1. `msr_company_header` report layouts - unblocks `xn_auditree_erp`
2. Cybrosys bug report for `base_accounting_kit` - longest external lead time,
   also unblocks `dynamic_accounts_report`
3. Decide `bi_crm_task` and `query_deluxe` (buy or drop)
4. Uninstall `document_management_system` (empty table, nothing references it)
5. Turn section 3 into a real production runbook
6. Manual UI verification against known-correct figures from the 17 instance
