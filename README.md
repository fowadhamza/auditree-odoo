# Auditree ERP

Auditree ERP is a customized business management system built on **Odoo 17 (Community Edition)**. It combines Odoo's standard business apps with a set of custom modules tailored for HR, payroll, and accounting workflows.

This document is a guide to what's currently in the application, what's available but not turned on yet, known issues to address, and recommended next steps.

---

## What's Running Today (Core Odoo Apps)

These are standard Odoo applications currently active in the system:

| App | What it's for |
|---|---|
| Employees | Core employee records and org structure |
| Recruitment / Online Jobs | Managing job postings and applicants |
| Attendances | Employee clock-in/clock-out tracking |
| Time Off | Leave requests and approvals |
| Employee Contracts | Employment contract records |
| Expenses | Employee expense claims |
| Skills Management | Tracking employee skills/competencies |
| Invoicing | Core billing and invoices |
| CRM | Sales leads and pipeline management |
| Sales | Sales orders and quotations |
| Purchase | Purchase orders |
| Inventory | Stock/warehouse management |
| Project / To-Do | Task and project tracking |
| Contacts | Central address book |
| Calendar | Scheduling and events |
| Discuss | Internal messaging/notifications |
| Surveys | Feedback and survey forms |
| Website | Public-facing company website |

---

## Custom Features Installed

On top of the standard apps above, the following custom-built or vendor add-on modules are active:

### HR & Payroll
| Module | What it does |
|---|---|
| Odoo 17 HR Payroll | Employee payroll records and payslips |
| Odoo17 Payroll Accounting | Links payroll to accounting entries |
| Open HRMS Loan Management | Employee loan requests with salary deduction |
| Open HRMS Loan Accounting | Accounting entries for employee loans |
| Open HRMS Advance Salary | Salary advance requests |
| Open HRMS Branch Transfer | Transfer employees between branches |
| OpenHRMS Employee Info | Extra fields on employee records |
| Open HRMS Resignation | Resignation workflow with approvals |
| Open HRMS Official Announcements | Company-wide announcements to employees |
| Open HRMS Reminders Todo | Reminders for important HR events/deadlines |
| Open HRMS Employee Insurance | Track insurance deductions from salary |
| Job Offer Letter | Generate and send offer letters to applicants |
| Open HRMS Leave Request Aliasing | Create leave requests from incoming emails |
| Open HRMS Multi-Company | Multi-company HR support |
| Open HRMS Employees From User | Auto-create employee records for new users |
| Open HRMS Employee Documents Expiry | Alerts for expiring employee documents |
| Hide Any Menu User Wise | Hide menu items based on user permissions |

### Accounting & Finance
| Module | What it does |
|---|---|
| Odoo 17 Full Accounting Kit | Extended accounting reports, journals, budgets |
| Odoo 17 Budget Management | Budget planning and tracking |
| Advanced Cash Flow Statements | Multi-level cash flow reports (PDF/Excel) |
| Bank Customization | Customized bank/payment details |
| Company Header | Custom headers on reports and documents |

### CRM & Sales
| Module | What it does |
|---|---|
| CRM Kit | Extended CRM features, commission plans |
| CRM Dashboard | Visual CRM analytics and reporting |
| Create Task from Lead | Turn a CRM lead directly into a project task |

### IT & Operations
| Module | What it does |
|---|---|
| Equipment Request & IT Operation | Employee equipment requests and approvals |
| PostgreSQL Query Deluxe | Run database queries directly from the UI (admin tool) |

### Look & Feel
| Module | What it does |
|---|---|
| MuK Backend Theme | Overall admin interface theme |
| MuK AppsBar | Sidebar app launcher |
| MuK Chatter | Improved message/log panel |
| MuK Colors | Theme color customization |
| MuK Dialog | Full-screen dialog option |

### Core Auditree Layer
| Module | What it does |
|---|---|
| Auditree ERP | Main custom module tying together HR, attendance, recruitment, and project management for Auditree |
| Auditree USER Custom ERP | Custom user-view customizations |

---

## Available But Not Turned On

These modules are already present in the codebase but not currently installed/active. They may be worth evaluating as "quick win" additions:

| Module | What it does |
|---|---|
| Open HRMS HR Dashboard | Consolidated HR analytics dashboard |
| Open HRMS Custody | Track company property assigned to employees |
| Open HRMS Gratuity Settlement | Gratuity calculation on employee exit |
| Document Management System | Centralized document storage/management |
| Odoo 17 Assets Management | Fixed asset tracking and depreciation |
| Odoo 17 Account Bank Statement Import | Import bank statements (CSV/XLSX) |
| Odoo17 Dynamic Accounting Reports | Ledgers, trial balance, balance sheet reports |
| Accounting Dashboard Odoo17 | Visual accounting dashboard |
| Odoo17 Invoice Format Editor | Custom invoice templates |
| MSR - Recruitment Checklist | Checklist-driven hiring process |
| Open HRMS Core | Core HRMS module (see note below) |
| Backend Base | Alternate admin theme |
| Advanced Property Management, Property Management, Insafety Property Rent | Three different property-management modules (renting/selling) |
| Charity Forms | Charity donation form management |

> **Note:** `Open HRMS Core` is uninstalled even though it's typically a dependency for other active OHRMS modules — worth checking before enabling any more HR modules from this vendor family.
>
> **Note:** There are three overlapping property-management modules on disk, all uninstalled. If property management becomes a need, pick one rather than enabling all three.

---

## Known Issues / Technical Debt

| Issue | Why it matters |
|---|---|
| Admin password stored in plain text (dev & prod config files) | Should be rotated and handled as a secret, not committed in plain form |
| Some backend Python dependencies are outdated with known security advisories (cryptography, Pillow, Werkzeug, requests, urllib3, PyPDF2) | Should be upgraded to patched versions |
| Leftover debug `print()` statement in the Auditree ERP employee code | Minor cleanup, no functional impact |
| A security file is misnamed (`secutity.xml` instead of `security.xml`) | Cosmetic, currently works because the reference matches, but confusing |
| A couple of employee-related search queries aren't scoped to a single company | Could show cross-company data in a multi-company setup |
| Production server's operating system (Ubuntu 22.10) is past end-of-life | No more security patches from Ubuntu — this is the most significant risk found and should be prioritized |
| Some vendor module asset files have overly-open file permissions | Low risk (static images/fonts only), but should be tightened |
| Unused duplicate addons folder exists on the production server | Not actively loaded, just disk clutter — safe to clean up later |

---

## Infrastructure Snapshot

- **Local development**: Odoo 17, WSL-based environment.
- **Production**: DigitalOcean-hosted server, running as a managed background service.
- As of the last review, **the code running in production is verified identical, file-for-file, to what's in this repository** — local development is a reliable mirror of production.

---

## Recommended Next Steps

1. **Security & hygiene (highest priority)**: rotate the admin password, update outdated dependencies, fix the minor code issues above, and plan an operating system upgrade for the production server.
2. **Git remote setup**: push this repository to a hosted remote (GitHub/GitLab) so history is backed up off the local machine.
3. **Quick wins**: evaluate enabling high-value dormant modules (HR Dashboard, Assets Management, Dynamic Accounting Reports, Document Management) — after resolving the `Open HRMS Core` dependency question first.
4. **New feature additions**: consider longer-term additions such as Appraisals, Approvals workflows, Digital Signatures, or a Helpdesk system, depending on business needs.
5. **Odoo version upgrade**: evaluate moving beyond Odoo 17 in the future as part of a broader modernization effort.
