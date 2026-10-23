# Handoff -- state of work at 2026-10-23

Written on the old (IBM) laptop so work can continue on the new one. Read CLAUDE.md first;
this file is the "where were we" on top of it. Delete or rewrite it once it is stale.

---

## 1. Branches

| Branch | What | Status |
|---|---|---|
| `main` | Production code: tag `prod-2026-10-20` (`bdd1838`) + one commit that stops tracking `sh_backend_base` (`4cb4195`) | Pushed |
| `feature/recruitment` | **Active work.** New module `xn_recruitment` + this file + CLAUDE.md updates + `scripts/laptop-migration/` | Pushed after this commit (run `git push origin feature/recruitment`) |
| `wip/old-laptop-2026-10-23` | Uncommitted work found on the old laptop (section 6). Not reviewed, not deployed (except the `hrms_dashboard` file, which IS on prod) | Push with `git push -u origin wip/old-laptop-2026-10-23` |
| `feature/it-helpdesk` | `xn_it_helpdesk` + OCA `helpdesk_mgmt`. Built 2026-10-15, **not on prod** | Built on the old git history; rebase onto `main` before deploying |
| `laptop-migration` | Encrypted bundle used to move the dev environment | Delete once the new laptop works: `git push origin --delete laptop-migration` |

Prod tags so far: `prod-2026-10-19` (fingerprint-verified), `-19b`, `-19c`, `-19d`, `prod-2026-10-20`.
Rule (CLAUDE.md section 8): `main` = what is live; tag every deploy.

## 2. sh_backend_base -- read before switching branches

The Softhealer theme is installed on prod but no longer tracked in git (licence). Any
checkout that goes from a commit that tracked it to one that does not **deletes it from
disk**. If `custom/addons/sh_backend_base/__manifest__.py` is missing:

```bash
git restore --source=4cb4195~1 --worktree custom/addons/sh_backend_base
```

Never run `deploy/04b_deploy_code_fresh.sh` without it on disk: the deploy wipes `custom/`
on the VM and would remove an installed module from prod.

A history purge of the module was done on GitHub on 2026-10-18; the new laptop (restored
from a pre-purge bundle) merged the old history back on 2026-10-19. Decision: keep the old
history, just stop tracking it. Do not attempt another purge unless every clone is re-synced.

## 3. Recruitment module (`custom/addons/xn_recruitment`)

Built from HR's questionnaire answers (Ayesha, Oct 2026). Full design in the module's
README.md and manifest description. **Never installed or run yet** -- written on a laptop
where WSL could not be used.

What it does (HR's top three first):
1. Rejection email on refusal at any stage (HR's 8 refuse reasons all carry the template).
2. Moving a candidate into Round 1 / Round 2 / Final / Decision emails that round's panel
   the CV + previous round's feedback (no salary), gives them access, 1-day feedback to-do.
3. Reports: Hiring Status (funnel per position), Daily Movement, Interviews, Source
   Performance; optional daily email (cron installed inactive).
Plus candidate fields (notice, qualification, CA/ACCA, experience, CTC hidden from
interviewers), job requisition fields, Technical / Non-Technical panels, agencies with fee
rule, referrer, hold, reapply-within-6-months flag, bond, did-not-join.

### Install and test (new laptop, WSL)

```bash
cd ~/Projects/Auditree
git fetch origin && git switch feature/recruitment
ls custom/addons/sh_backend_base/__manifest__.py || git restore --source=4cb4195~1 --worktree custom/addons/sh_backend_base
# the local DB is a prod copy with prod's mail server: turn it off or real people get email
psql -U fowadhamza -d AUDITREE_LIVE_NEW -c "UPDATE ir_mail_server SET active = false;"
./start-local.sh stop
cd auditreelive-server
python3 odoo-bin --config=../local-dev.conf -d AUDITREE_LIVE_NEW -i xn_recruitment --stop-after-init 2>&1 \
  | grep -E "ERROR|CRITICAL|Traceback|xn_recruitment|Modules loaded"
cd .. && ./start-local.sh start
```

UI checks:
- Recruitment > Configuration > Interview Panels: right people per round (ambiguous first
  names are skipped and logged).
- A job's Requisition tab; set its panel.
- New candidate -> "Approve And Move To Next" up to Round 1 -> chatter says "Sent to ...",
  email visible in Settings > Technical > Emails.
- Give Feedback -> move to Round 2 -> email contains Round 1 feedback.
- Refuse -> the rejection email box is ticked.
- Recruitment > Reporting > Hiring Status.

### Open points before go-live
- **Sender**: prod's only SMTP is Titan with From filter `no-reply@auditree.org`; hr@ gets
  rewritten unless a Microsoft 365 outgoing server for auditree.com is added (module README).
- **Moving candidates** uses xn_auditree_erp's "Approve And Move To Next" (sequence + 1),
  visible only to Recruitment **Administrators** -- HR needs that role. The hook numbers
  HR's stages 1..9 consecutively for this.
- **Panels**: jobs with "audit" in the name got Technical, others Non-Technical -- HR to check.
  The tracker shows **Sowmya** doing Round 2 / Final interviews; she is not in HR's panel
  answer. Danyal does the HR initial calls.
- **Daily email cron** is inactive; enable on prod, set next run 08:00 IST.

### Phase 2 (not started)
- CV intake from hr@ / job sites with automatic field filling (HR's biggest frustration);
  `xn_ai_core` could do the extraction.
- Import of the hiring tracker (section 4).
- COO offer approval, agency fee + referral bonus due dates.

## 4. Hiring tracker import (analysed, not built)

File: `Hiring tracker 2026 (1).xlsx` at the repo root on the old laptop. **Not in git**
(candidates' personal data) -- copy it across by hand.

- One sheet per round, rows copied forward: `2025` (122 rows, actually Feb 2026 cold-call
  list), `HR Initiall Call` (394), `Round 1` (92), `Round 2` (29), `Final round` (11);
  `Decision Making Round` and `Selected` are empty; `Sheet1` is the Teams update table.
- **386 unique candidates** (matched by email, else phone). Furthest round: Final 10
  (6 rejected, 4 shortlisted), R2 19, R1 63, HR call 291, cold call 3.
- Plan: one applicant per person at the furthest stage, created directly (no emails, context
  `xn_skip_reapply_check`), one feedback record per round (interviewer, date, comment,
  status); rejected -> refused with a reason picked by keyword (CTC / communication / else
  "Not suitable"), full comment kept. Sources: LinkedIn/Naukri/Indeed/OLX; "Vikash
  Recruitment" / "AJ Recruitment" -> existing agencies; Victorypeak, EazeRecruit -> new
  agencies; "Reference from X" (also misspelt "Referance") -> Employee Referral + referrer.
- Parsing needed: notice ("Immediate joiner" = 0, "1 month" = 30), experience ("4 years
  (Including Articleship)", "Fresher"), CA attempts ("NA"), CTC -- 449 of 1282 values are
  not "N LPA" ("9 to 10 LPA", "3.3 L per month", "25K per month Stipend", "1.5K (Riyal)",
  "As per company standards"): convert when clear (range -> lower, monthly x 12), keep the
  original text in the notes.
- **Questions for HR before building it**: where are the CV files ("Resume Link" holds
  file names only)? Which of the 4 final-round shortlisted joined, and when? Is there an
  older 2025 tracker file? Add Sowmya to the panels?

## 5. Production facts learnt this week (also in CLAUDE.md section 8)

- Fingerprint check 2026-10-19: prod matched commit `6fe956b` except 4 `xn_hr_dashboard`
  files; files on prod are CRLF because deploys copy the WSL working tree.
- Comparing from Windows: Git for Windows has `core.autocrlf=true` system-wide (pass
  `-c core.autocrlf=false`) and its `sha256sum` prints `*./file`.
- `local Odoo` uses system python3 (3.12), not the 3.10 venv.

## 6. What went on `wip/old-laptop-2026-10-23`

Uncommitted changes found on the old laptop, committed so nothing is lost. Line endings
normalised to the repo's LF where the committed file was LF.

| Path | Notes |
|---|---|
| `custom/addons/hrms_dashboard/models/hr_employee.py` | **Identical to what prod runs** -- deployed but never committed. Belongs on `main`. |
| `custom/addons/xn_hr_dashboard/...` (4 files) | ~145 changed lines, newer than prod (dated 2026-10-04/06). Not deployed. |
| `custom/addons/xn_ai_graph/models/...` + new `graph_document.py` | Sept 19 work on SharePoint/document search. Not deployed. |
| `custom/addons/xn_account_dashboard/` | "Auditree Accounting Overview" module, never committed, not on prod. |
| `custom/addons/xn_recruitment_bridge/` | WordPress -> Odoo job application endpoints, never committed, not on prod. |

## 7. Not in git -- copy by hand if needed

Already inside the encrypted migration bundle (packed 2026-10-18): `local-dev.conf`,
`start-local.sh` (old sudo password on line 32), `deploy/` incl. `deploy/secrets/prod.env`.
Newer than the bundle / not in it: `Hiring tracker 2026 (1).xlsx`,
`Assets Master Sheet - 2026 to 2027.xlsx`, the Zoho Books Q&A folder/zip, `asset-import/`.

## 8. Notes for Claude on the new laptop

- The "no WSL commands" memory came from the IBM-managed laptop's security monitoring. If the
  new laptop is not managed, delete that memory and its MEMORY.md line.
- Claude Code memory and sessions were migrated separately (`claude/` folder on the
  `laptop-migration` branch, `restore-claude.ps1`).
- `~/prod-fp.txt` and `~/prod-files.txt` on the old laptop hold the 2026-10-19 prod
  fingerprints; regenerate rather than rely on them.
