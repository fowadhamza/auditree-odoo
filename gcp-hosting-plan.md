# Host Auditree ERP (Odoo 17) on Google Cloud

## Overview

Migrate the current native (non-Docker) Odoo 17 Community deployment — `auditreelive` system user, code under `/opt/odoo17/auditreelive/{auditreelive-server,custom}`, systemd-managed, Nginx-fronted — to a Google Cloud **Compute Engine** VM. This matches the existing architecture (`auditreelive-server.conf`, `auditreelive-server/debian/odoo.service`, `start.sh`) so no containerization rework is needed. Migration artifacts are already exported and sitting in the repo root: `AUDITREE_LIVE_NEW.dump` (DB), `AUDITREE_FILESTORE.tar.gz` (attachments), `AUDITREE_ADDONS.tar.gz` / `auditreelive-server.tar.gz` (code).

**Scope:** infrastructure provisioning, deployment, and cutover. No application code changes.

---

## Sub-Tasks

---

### Sub-Task 1 — GCP project & architecture decision

**Intent**
Set up billing/project and decide two open questions before provisioning: (a) Compute Engine VM running Postgres locally vs. a separate **Cloud SQL for PostgreSQL** instance, and (b) machine size.

**Expected Outcomes**
- GCP project created with billing enabled
- Decision recorded: DB location (local on VM vs Cloud SQL) and VM size (e2-medium as a starting point: 2 vCPU / 4GB, resize later based on `htop`/load)

**Todo List**
1. Create/select a GCP project, enable billing
2. Enable required APIs: Compute Engine API (+ Cloud SQL Admin API if using Cloud SQL)
3. Decide: Cloud SQL (managed backups/HA, extra cost, extra network hop) vs local Postgres on the VM (matches current setup exactly, simplest lift-and-shift)
4. Decide VM machine type and boot disk size (start: e2-medium, 30–50GB SSD persistent disk — current filestore tarball is ~30MB, dump ~13MB, but leave room for growth)

**Relevant Context**
- Current production conf: [auditreelive-server.conf](auditreelive-server.conf) (http_port 8001, `dbfilter=AUDITREE_LIVE_NEW`)
- Project `auditree-prod` created, billing account `01095A-88EBC7-093848` linked, `compute.googleapis.com` enabled. Region: `us-central1`. Decision: local Postgres on the VM (no Cloud SQL).
- `auditreelive-server/requirements.txt` — packages pinned to Ubuntu 22.04 / Debian 11 versions → **use Ubuntu 22.04 LTS image** on the VM to match
- **Billing:** new GCP customers get $300 in free trial credit (valid until used up or ~90 days, whichever first — confirm exact expiry at signup). An e2-medium VM + 50GB disk runs ~$25–30/month, comfortably within budget for the whole trial period; skip Cloud SQL to preserve credit (Cloud SQL adds meaningful cost on top)
- The separate **Compute Engine Always Free tier** (1 e2-micro/month, `us-west1`/`us-central1`/`us-east1` only) is a different program from the $300 trial and too small to run Odoo — don't rely on it for this deployment

**Status:** [x] done

---

### Sub-Task 2 — Provision the Compute Engine VM & networking

**Intent**
Create the VM, a static external IP, and firewall rules restricting access to only what's needed (SSH, HTTP/HTTPS).

**Expected Outcomes**
- VM running Ubuntu 22.04 LTS, reachable via a reserved static IP
- Firewall allows: 22 (SSH, ideally restricted to your IP or via IAP), 80/443 (public), nothing else exposed (Odoo's 8069/8001 stay bound to localhost behind Nginx)

**Todo List**
1. `gcloud compute instances create auditreelive-prod --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud --machine-type=e2-medium --boot-disk-size=50GB`
2. Reserve a static external IP and attach it to the VM
3. Create/confirm firewall rules for tags `http-server`/`https-server` (80/443) and a restricted SSH rule
4. (Optional) Use Identity-Aware Proxy (IAP) for SSH instead of exposing port 22 publicly

**Relevant Context**
- No existing Terraform/deployment scripts found in repo — this will be first-time manual (or `gcloud`) provisioning
- Deployed: project `auditree-prod`, VM `auditreelive-prod` in `us-central1-a`, static IP `34.63.212.242` (reserved as `auditreelive-ip`). Firewall: `allow-http-https` (80/443, public), `allow-ssh-restricted` (22, scoped to admin's public IP); the project's default `default-allow-ssh` (0.0.0.0/0) rule was disabled to enforce the restriction. Direct SSH verified working (`gcloud compute ssh auditreelive-prod`).

**Status:** [x] done

---

### Sub-Task 3 — Install system dependencies on the VM

**Intent**
Install PostgreSQL (if self-hosting the DB), Python, build deps, wkhtmltopdf, and Nginx — mirroring what the current server needs.

**Expected Outcomes**
- `python3.10` + `venv` available
- PostgreSQL 14/15 installed and running (skip if using Cloud SQL)
- `wkhtmltopdf` installed (odoo.log already warns "You need Wkhtmltopdf to print a pdf version of the reports")
- Nginx installed

**Todo List**
1. `apt update && apt install -y python3-venv python3-dev python3-pip build-essential libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libssl-dev libpq-dev`
2. Install PostgreSQL: `apt install -y postgresql`, create a `fowadhamza`-equivalent production DB role (e.g. `auditreelive`) with a strong password
3. Install `wkhtmltopdf` (0.12.6 with patched Qt — the version odoo.js reports needing; download the correct `.deb` for Ubuntu 22.04, not the apt default which lacks patched Qt)
4. `apt install -y nginx`
5. Create the `auditreelive` system user: `adduser --system --group --home /opt/odoo17/auditreelive auditreelive`

**Relevant Context**
- [auditreelive-server/requirements.txt](auditreelive-server/requirements.txt) — exact pinned versions to `pip install` inside the venv
- Current local log warning about missing wkhtmltopdf confirms this was never fully configured even in dev — verify it in the new prod env
- Done: `postgresql` 14, `nginx`, `python3-venv`, build deps, and `wkhtmltox` 0.12.6.1 (patched Qt) installed on the VM. System user `auditreelive` (uid 114) created with home `/opt/odoo17/auditreelive`. Postgres superuser role `auditreelive` created and password set (stored in untracked `deploy/secrets/prod.env`, git-ignored).
- Lesson: nested quoting through PowerShell → `wsl.exe` → `bash -lc` → `gcloud compute ssh --command=` is unreliable for anything with internal quotes/`$()`. Workflow going forward: write scripts under `deploy/` locally and run them with a plain `wsl.exe -- bash deploy/script.sh` (or `gcloud compute scp` + remote `bash /tmp/script.sh`) instead of inlining complex commands.
- Note: a fresh GCE Ubuntu image runs its own background `apt-get`/unattended-upgrade shortly after boot — the first manual `apt install` can appear to hang/fail on the dpkg lock; it actually keeps running server-side even if the local SSH session output looks interrupted. Poll with `dpkg -l <pkg>` rather than assuming failure.

**Status:** [x] done

---

### Sub-Task 4 — Deploy code

**Intent**
Get `auditreelive-server` + `custom/addons` onto the VM under `/opt/odoo17/auditreelive/`, matching the paths already hardcoded in `auditreelive-server.conf` and `start.sh`.

**Expected Outcomes**
- `/opt/odoo17/auditreelive/auditreelive-server/` and `/opt/odoo17/auditreelive/custom/` populated
- Python venv created and all `requirements.txt` packages installed
- Ownership set to `auditreelive:auditreelive`

**Todo List**
1. Either `git clone` the repo on the VM (if it's under version control remotely) or `scp`/upload `auditreelive-server.tar.gz` + `AUDITREE_ADDONS.tar.gz` and extract into place
2. `python3 -m venv /opt/odoo17/auditreelive/venv && source .../venv/bin/activate && pip install -r auditreelive-server/requirements.txt`
3. `chown -R auditreelive:auditreelive /opt/odoo17/auditreelive`
4. Copy [auditreelive-server/start.sh](auditreelive-server/start.sh) or adopt the systemd unit from Sub-Task 6 instead (prefer systemd over the raw shell script for prod)

**Relevant Context**
- [start.sh](auditreelive-server/start.sh) already assumes exactly this path layout and the `auditreelive` user via `sudo -u auditreelive`
- **Important:** the repo-root pre-built `auditreelive-server.tar.gz`/`AUDITREE_ADDONS.tar.gz` turned out to be **stale** — their `requirements.txt` pinned `gevent==21.8.0` for Python 3.10 (no prebuilt wheel, fails to build from source due to a Cython/setuptools incompatibility), while the live checkout pins `gevent==22.10.2` (has a manylinux wheel, installs cleanly). Deployed instead by building fresh tarballs from the live checkout (`deploy/04b_deploy_code_fresh.sh`) — don't reuse the old repo-root tarballs for this deployment.
- Done: fresh code deployed to `/opt/odoo17/auditreelive/{auditreelive-server,custom}`, venv created at `/opt/odoo17/auditreelive/venv` (Python 3.10), all `requirements.txt` packages installed (including `pandas` which the custom `hrms_dashboard` addon needs), ownership set to `auditreelive:auditreelive`.

**Status:** [x] done

---

### Sub-Task 5 — Restore the database and filestore

**Intent**
Load `AUDITREE_LIVE_NEW.dump` into the new Postgres instance and extract `AUDITREE_FILESTORE.tar.gz` into the data_dir so attachments resolve correctly.

**Expected Outcomes**
- `AUDITREE_LIVE_NEW` database exists and matches the dump's contents
- Filestore extracted to `<data_dir>/filestore/AUDITREE_LIVE_NEW/` so attachment records match files on disk

**Todo List**
1. `createdb -O auditreelive AUDITREE_LIVE_NEW`
2. `pg_restore` (or `psql <` if it's a plain-text dump — check with `file AUDITREE_LIVE_NEW.dump`) into the new DB
3. Create the data dir (e.g. `/opt/odoo17/auditreelive/.local/share/Odoo`) and extract `AUDITREE_FILESTORE.tar.gz` under `filestore/AUDITREE_LIVE_NEW/`
4. Set `data_dir` in the prod conf to match, `chown` to `auditreelive`

**Relevant Context**
- Local dev `data_dir=/home/fowadhamza/.local/share/Odoo` in [odoo.conf](odoo.conf) — prod conf currently has no `data_dir` set, needs one added
- `AUDITREE_LIVE_NEW.dump` (~13MB) and `AUDITREE_FILESTORE.tar.gz` (~30MB) both in repo root already
- Done: `AUDITREE_LIVE_NEW` DB created (owner `auditreelive`) and restored via `pg_restore` from the custom-format dump (`deploy/05_restore_db_filestore.sh`); verified 179 installed modules post-restore. Filestore extracted to `/opt/odoo17/auditreelive/.local/share/Odoo/filestore/AUDITREE_LIVE_NEW/`, owned by `auditreelive`. `data_dir` for the prod conf still needs to be set in Sub-Task 6 to `/opt/odoo17/auditreelive/.local/share/Odoo`.

**Status:** [x] done

---

### Sub-Task 6 — Production config & systemd service

**Intent**
Finalize `/etc/auditreelive-server.conf` on the VM and run Odoo as a systemd service (more robust than the plain `start.sh` for auto-restart/boot).

**Expected Outcomes**
- Config at `/etc/auditreelive-server.conf` with a real `admin_passwd` (not committed to git), `db_host`/`db_user`/`db_password` pointing at the DB (localhost or Cloud SQL private IP), `data_dir`, `addons_path` matching deployed paths
- `systemctl enable --now odoo` keeps it running across reboots/crashes

**Todo List**
1. Copy [auditreelive-server.conf](auditreelive-server.conf) to `/etc/auditreelive-server.conf` on the VM, fill in real `admin_passwd`, `db_password`, add `data_dir`
2. Adapt [auditreelive-server/debian/odoo.service](auditreelive-server/debian/odoo.service) — update `User=`/`Group=` to `auditreelive`, `ExecStart` to the venv's `odoo-bin` and the `/etc/auditreelive-server.conf` path
3. `systemctl daemon-reload && systemctl enable --now odoo`
4. Tail `/var/log/auditreelive/auditreelive-server.log` to confirm "HTTP service ... running" and no traceback

**Relevant Context**
- `admin_passwd` currently committed in plaintext in [auditreelive-server.conf](auditreelive-server.conf) — **rotate this for production**, don't reuse the committed one
- `.gitignore` should already exclude prod secrets — verify `auditreelive-server.conf` (the real one, not `.example`) isn't tracked going forward
- Done: rotated `admin_passwd`/`db_password` generated and deployed to `/etc/auditreelive-server.conf` (mode 640, `root:auditreelive`) with `data_dir`, `db_host=localhost`, `db_user=auditreelive`, `proxy_mode=True`, and `addons_path` pointing at the deployed venv paths. Systemd unit `odoo.service` installed (`User=auditreelive`, `ExecStart` uses the venv's Python + `odoo-bin`, `Restart=on-failure`), enabled and running. Verified: `systemctl status` active/running, `curl http://127.0.0.1:8001/web/login` → 200, log shows "179 modules loaded" / "Registry loaded" with no tracebacks (only benign deprecation warnings from older third-party addons).

**Status:** [x] done

---

### Sub-Task 7 — Nginx reverse proxy + HTTPS

**Intent**
Terminate TLS at Nginx, proxy to Odoo's `http_port` (8001) and the longpolling port, and get a Let's Encrypt cert.

**Expected Outcomes**
- `https://<domain>` serves Odoo; HTTP redirects to HTTPS
- Websocket/longpolling (`/websocket` or `/longpolling`) proxied correctly for Discuss/live features
- Auto-renewing cert via certbot

**Todo List**
1. Write an Nginx server block proxying `/` → `127.0.0.1:8001` and `/websocket` → the longpolling port (set `--proxy-mode` / `workers` + `longpolling_port` in the conf if using multi-worker mode)
2. `certbot --nginx -d <domain>` for TLS
3. Add standard Odoo proxy headers (`X-Forwarded-Host`, `X-Forwarded-For`, `X-Forwarded-Proto`) and set `proxy_mode = True` in the Odoo conf so it trusts them

**Relevant Context**
- Current conf runs single-process (no `workers` set) — fine for low traffic, but longpolling/websocket needs `workers > 0` with a separate `longpolling_port` for real concurrency; decide based on expected user count

**Status:** [ ] pending

---

### Sub-Task 8 — DNS cutover

**Intent**
Point the production domain at the new VM's static IP once smoke-tested.

**Expected Outcomes**
- DNS A record for the domain resolves to the GCP static IP
- Old host (if any) decommissioned only after confirming the new one is stable

**Todo List**
1. Smoke-test via the VM's IP directly (or a temp `/etc/hosts` entry) before flipping DNS
2. Update the A record, lower TTL beforehand to speed up propagation
3. Verify HTTPS cert covers the final domain

**Status:** [ ] pending

---

### Sub-Task 9 — Backups & monitoring

**Intent**
Ensure the migration doesn't regress on backup coverage — set up automated DB + filestore backups and basic uptime/log monitoring.

**Expected Outcomes**
- Nightly `pg_dump` (or Cloud SQL automated backups) retained on a rolling window, stored off-VM (e.g. a GCS bucket)
- Filestore backed up alongside the DB (attachments live on disk, not in Postgres)
- Basic alerting if the Odoo service or Nginx goes down (Cloud Monitoring uptime check, or a simple systemd `OnFailure=` + email/webhook)

**Todo List**
1. Cron job: `pg_dump` → gzip → upload to a GCS bucket (`gsutil cp`), rotate old backups
2. Cron/rsync job to snapshot the filestore directory to the same bucket
3. Set up a Cloud Monitoring uptime check against the public HTTPS endpoint
4. (Optional) Compute Engine persistent disk snapshot schedule as a whole-VM safety net

**Status:** [ ] pending

---

### Sub-Task 10 — Post-launch validation & rollback plan

**Intent**
Confirm the migrated instance is fully functional and have a documented way back if something's wrong.

**Expected Outcomes**
- Login works, key modules (Payroll, Accounting, CRM, custom `xn_auditree_erp`) load without errors
- Rollback plan documented: keep the old environment untouched/available until the new one is proven stable for some period

**Todo List**
1. Log in, spot-check Employees, Payroll, Accounting, CRM, and the custom Auditree modules
2. Check `odoo.log`-equivalent (`/var/log/auditreelive/auditreelive-server.log`) for warnings/tracebacks under real use
3. Keep the previous hosting environment running (read-only or paused) for an agreed grace period before decommissioning
4. Document the rollback steps (repoint DNS back, restore from the pre-cutover backup) in case of a critical issue

**Status:** [ ] pending

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Python/OS package version mismatch (requirements.txt pinned to Ubuntu 22.04/Debian 11) | Medium | Medium | Use Ubuntu 22.04 LTS image, install from `requirements.txt` inside a venv rather than system-wide |
| `admin_passwd` / DB credentials currently committed in plaintext in repo | Certain | High | Rotate all secrets before going live; keep the real prod conf out of git |
| Filestore/DB restored out of sync (attachments missing) | Low–Medium | Medium | Restore both from the same export snapshot; verify a sample of `ir.attachment` records resolve to real files |
| Single VM = single point of failure | Certain (by design) | Medium | Acceptable for current scale; mitigated by backups + disk snapshots; revisit HA later if needed |
| Longpolling/websocket misconfigured behind Nginx | Medium | Low | Test Discuss/live notification features explicitly after cutover |

## Files Involved

- [odoo.conf](odoo.conf) — local dev reference config (paths won't match prod)
- [auditreelive-server.conf](auditreelive-server.conf) — base for the real `/etc/auditreelive-server.conf` on the VM (secrets need rotating)
- [auditreelive-server/start.sh](auditreelive-server/start.sh) — reference for the run command; superseded by systemd in Sub-Task 6
- [auditreelive-server/debian/odoo.service](auditreelive-server/debian/odoo.service) — base systemd unit to adapt
- [auditreelive-server/requirements.txt](auditreelive-server/requirements.txt) — Python deps to install in the VM's venv
- `AUDITREE_LIVE_NEW.dump`, `AUDITREE_FILESTORE.tar.gz`, `AUDITREE_ADDONS.tar.gz`, `auditreelive-server.tar.gz` — migration artifacts already present at repo root
