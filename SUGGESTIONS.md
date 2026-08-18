# Suggestions to Improve the Auditree Odoo Codebase

After a thorough review of the custom modules, configuration, deployment setup, and overall project structure, here are prioritised suggestions grouped by category.

---

## 🔴 Priority 1 — Security & Stability (Fix Now)

### 1. Rotate the admin master password
The `odoo.conf` has `admin_passwd = admin`. This is the Odoo **database management** password — anyone who guesses it can create, drop, or restore databases.

**Action:** Set a strong, unique password in `odoo.conf` and the production `.conf`. Consider disabling the database manager entirely in production with `list_db = False`.

### 2. Upgrade pinned Python dependencies with known CVEs
The [requirements.txt](file:///home/fowadhamza/Projects/Auditree/auditreelive-server/requirements.txt) pins very old versions:

| Package | Pinned | Risk |
|---|---|---|
| `cryptography` | 3.4.8 | Multiple critical CVEs since then (latest: 50.x) |
| `Pillow` | 9.0.1 / 9.4.0 | RCE vulnerabilities patched in later versions |
| `Werkzeug` | 2.0.2 | Cookie parsing, debugger vulnerabilities |
| `requests` | 2.25.1 | MITM / proxy credential leak issues |
| `urllib3` | 1.26.5 | Header injection, SSRF patches |
| `PyPDF2` | 1.26.0 / 2.12.1 | Superseded by `pypdf`; several DoS bugs |
| `pyopenssl` | 21.0.0 | Deprecated; use `ssl` stdlib or newer `cryptography` |

**Action:** Create a `requirements-safe.txt` with minimum-patched versions and test in dev. At minimum, bump `cryptography`, `Pillow`, `Werkzeug`, and `requests`.

### 3. Production OS is past end-of-life
Ubuntu 22.10 (Kinetic) went EOL in July 2023. No more security patches.

**Action:** The GCP migration plan already targets Ubuntu 22.04 LTS — ensure the DigitalOcean server is decommissioned once GCP is live, or upgrade it to 22.04/24.04 LTS.

### 4. SQL constraint doesn't scope to company
```python
sql_constraints = [
    ('adhar_pan_uniq', 'unique (adhar_no, pan_no)', 
     'PAN, Adhar must be unique per company.'),
]
```
The message says "per company" but the constraint is global — if two companies share the same Odoo instance, employees with the same Aadhaar/PAN across companies would conflict.

**Action:** Change to `unique (adhar_no, pan_no, company_id)` if multi-company isolation is needed, or fix the error message to say "must be unique" (without "per company").

---

## 🟠 Priority 2 — Code Quality & Bugs

### 5. Remove leftover `print()` statements
Debug prints in production code create log noise and leak internal state:

| File | Line |
|---|---|
| [hr_applicant.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_erp/models/hr_applicant.py#L52) | `print("next_sequence", ...)` |
| [hr_applicant.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_erp/models/hr_applicant.py#L55) | `print("next_stage", ...)` |
| [property_building.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/insafity_property_rent/models/property_building.py#L298) | `print(invoice3)` |
| [product_template.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/equipment_request_it_operations/models/product_template.py#L24) | `print()` |

**Action:** Replace with `_logger.debug(...)` or remove entirely.

### 6. `_compute_hide_revert_back` sends emails as a side-effect
[hr_applicant.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_erp/models/hr_applicant.py#L24-L36) — the compute method for `is_hide_revert_back` **also sends an email** every time `stage_id` changes. Compute methods should be pure (no side effects). This means:
- Emails fire on every recompute, including page refreshes, imports, and ORM cache invalidations
- No try/except — a mail server error will crash the form

**Action:** Move the email-sending logic to an `@api.onchange` or override `write()` to trigger only on actual user-driven stage changes.

### 7. `lead_service.py` defines an empty model
[lead_service.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_erp/models/lead_service.py) defines `lead.service` with no fields and no methods — but it's not imported in `__init__.py` so it's dead code. However, it likely creates a database table.

**Action:** Either implement it or delete the file.

### 8. Unscoped `sudo().search([])` in cron jobs
In [hr_employee.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_erp/models/hr_employee.py#L37):
```python
employees = self.env['hr.employee'].sudo().search([])
```
This searches **all employees across all companies** with no domain filter. In a multi-company setup this processes records the current company shouldn't touch.

**Action:** Add `('company_id', 'in', self.env.companies.ids)` to the domain, or use `self.env['hr.employee'].search(...)` without `sudo()` to respect access rules.

### 9. `project_project.py` has class named `LeadService` for `project.project`
```python
class LeadService(models.Model):
    _inherit = "project.project"
```
And another `ResUsers` class in the same file that's entirely commented out.

**Action:** Rename the class to `ProjectProject` for clarity. Remove the dead `ResUsers` stub.

### 10. Inconsistent earnings data structure in payslip report
In [hr_payslip.py](file:///home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_erp/models/hr_payslip.py), `earnings` is a list of single-key dicts (`[{key: {amount: ...}}, ...]`) while `deductions` is a flat dict. This makes the zip-merge loop complex and fragile.

**Action:** Use the same data structure for both. A list of `(name, amount)` tuples or namedtuples would be cleaner.

---

## 🟡 Priority 3 — Developer Experience

### 11. Push the repo to a remote (GitHub/GitLab)
`git remote -v` returns nothing — this repo has **no remote**. All history is local-only. A disk failure loses everything.

> [!CAUTION]
> This is the single highest-risk developer experience gap. Push to a private GitHub/GitLab repo immediately.

### 12. Fix the typo: `secutity.xml` → `security.xml`
The security group file is misspelled. It works because the manifest references the misspelled name, but it confuses anyone reading the source tree.

**Action:** Rename the file and update the `__manifest__.py` reference.

### 13. Clean up commented-out code
Several files have blocks of commented-out code:
- `project_project.py`: `#is_freelancer=...` and empty `ResUsers`
- `hr_recruitment_view.xml`: commented-out Resume tab
- `res_users_view.xml` in `xn_auditree_erp`: commented-out `is_freelancer` field
- `__manifest__.py`: commented-out `res_users_view.xml` data entry

**Action:** Remove dead comments. Use git history to recover them if needed later.

### 14. Add a `.editorconfig` / linting
There's inconsistent formatting throughout the custom code (spaces around `=` in field definitions, trailing blank lines, mixed quoting). No linter is configured.

**Action:** Add `.editorconfig` and consider running `ruff` or `pylint-odoo` to enforce Odoo coding standards.

### 15. The `xn_auditree_erp` and `xn_user_custom` split is unclear
`xn_user_custom` exists solely to define `is_freelancer` on `res.users` and show it in a view. Meanwhile, `xn_auditree_erp` depends on it. This two-module structure adds complexity with no real benefit.

**Action:** Merge `xn_user_custom` into `xn_auditree_erp` (since it's already a dependency anyway).

### 16. Unused `lead_service.py` import is missing from `__init__.py`
The `models/__init__.py` doesn't import `lead_service`, so the `lead.service` model is never registered. Either the model is dead code or the import was accidentally removed.

**Action:** If `lead.service` is needed, add the import. If not, delete the file.

---

## 🔵 Priority 4 — Architecture & Scalability

### 17. Add record rules (ir.rule) for multi-company isolation
The `stage.approval.user` model grants **all internal users** full CRUD access via `ir.model.access.csv`, with no company-scoping `ir.rule`. Any user can edit any department's approval configuration across all companies.

**Action:** Add `ir.rule` records that filter by `company_id` for `stage.approval.user`, `hr.employee` custom fields, etc.

### 18. Add automated tests
There are **zero test files** in the custom modules. The probation notification cron, the stage-advance logic, and the payslip report builder are all untested.

**Action:** Create a `tests/` directory with at least:
- `test_probation_notification.py` — verify emails sent exactly once, at the right threshold
- `test_stage_advance.py` — verify approve/revert respects sequence boundaries
- `test_payslip_report.py` — verify the earnings/deductions merge logic

### 19. Consider splitting `hr_employee.py`
This single file contains:
- Employee model extensions (fields, constraints)
- Probation notification cron logic
- Employee type auto-promotion cron logic
- A `HrJob` class (unrelated to employees)

**Action:** Move `HrJob` to its own file. Extract the cron business logic into a service/mixin.

### 20. Move hardcoded days (75, 80, 90) to configurable settings
Probation thresholds are hardcoded in `mail_probation_reminder()`:
```python
thresholds = {
    'after_2_half_month': 75,
    'before_months': 80,
    'after_3months': 90,
}
```

**Action:** Move these to `ir.config_parameter` or editable fields on a settings model so HR admins can adjust without code changes.

---

## 🟢 Priority 5 — Operational Improvements

### 21. Enable `list_db = False` in production
With `list_db = True` (the default), anyone can see all database names at `/web/database/selector`. Combined with a weak admin password, this is a significant attack surface.

### 22. Set `log_level = warn` in production
The current log is chatty (every HTTP request logged at INFO level). Production should run at `warn` and use `log_handler` for specific module debugging.

### 23. Configure `proxy_mode = True` behind Nginx
Since Nginx fronts Odoo, `proxy_mode = True` is needed to correctly read `X-Forwarded-For` headers for IP logging and rate limiting.

### 24. Set up automated database backups
No backup cron or script was found. If the database is lost, recovery depends on the one-off `.dump` file in the repo root (which is gitignored).

**Action:** Add a daily `pg_dump` cron job writing to a cloud storage bucket (GCS if on GCP).

### 25. Consider enabling `web_responsive` fuzzy search for all users
The switch-to-web-responsive plan notes all users default to `canonical` search. Switching to `fuse` (fuzzy) search significantly improves app discoverability.

---

## Summary Priority Matrix

| Priority | Count | Theme |
|---|---|---|
| 🔴 **P1 — Fix Now** | 4 | Security: passwords, CVEs, EOL OS, SQL constraint |
| 🟠 **P2 — Soon** | 6 | Bugs: side-effect emails, dead code, unscoped searches |
| 🟡 **P3 — Plan** | 6 | DX: git remote, linting, module cleanup |
| 🔵 **P4 — Design** | 4 | Architecture: tests, access rules, configurability |
| 🟢 **P5 — Ops** | 5 | Production: logging, backups, proxy config |

> [!TIP]
> If you'd like me to implement any of these suggestions — for example, fixing the `print()` statements, refactoring the compute method, or setting up a test scaffold — just let me know which items to tackle first.
