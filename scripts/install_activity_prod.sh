#!/usr/bin/env bash
# Install activity tracking (xn_activity, plus xn_activity_joiner_leaver,
# which installs itself because xn_joiner_leaver is installed) on the
# production VM. Run ON the VM, as a user with sudo, after copying the
# tarball (built from a commit, not the working tree):
#
#   git -c core.autocrlf=false archive --format=tar <commit>:custom/addons \
#       xn_activity xn_activity_joiner_leaver | gzip > /tmp/activity.tar.gz
#   git -c core.autocrlf=false show <commit>:scripts/install_activity_prod.sh \
#       > /tmp/install_activity_prod.sh
#   gcloud compute scp /tmp/activity.tar.gz /tmp/install_activity_prod.sh \
#       auditreelive-prod-mum:/tmp/ --tunnel-through-iap --zone=asia-south1-a
#   gcloud compute ssh auditreelive-prod-mum --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/install_activity_prod.sh /tmp/activity.tar.gz
#
# Stages: pre-checks -> backup -> confirm -> unpack -> stop / install / start
# -> verify. It stops at the first problem. Odoo is down only between "stop"
# and "start" (about a minute). CONFIRM=yes skips the prompt.
#
# Success is judged by the exit code and the module state in the database,
# never by stdout: prod logs to a file, so stdout is empty (CLAUDE.md s8).
#
# Installing sends no email. The weekly HR digest cron is switched OFF after
# install for the pilot (DIGEST=on keeps it on); turn it on in Settings >
# Technical > Scheduled Actions at go-live. Nothing is collected until the
# agent is deployed to laptops from Agent Setup.

set -uo pipefail

TARBALL="${1:-/tmp/activity.tar.gz}"
DB="AUDITREE_LIVE_NEW"
ADDONS="/opt/odoo17/auditreelive/custom/addons"
LOG="/var/log/auditreelive/auditreelive-server.log"
CONF="/etc/auditreelive-server.conf"
PY="/opt/odoo17/auditreelive/venv/bin/python"
ODOO_BIN="/opt/odoo17/auditreelive/auditreelive-server/odoo-bin"
BACKUP_SCRIPT="/opt/auditree-backup/auditree_backup.sh"
BACKUP_STATUS="/var/backups/auditree/last_status"
BASE="https://odoo.auditree.com"
MODULES=(xn_activity xn_activity_joiner_leaver)
DEPENDS=(hr hr_holidays mail resource xn_joiner_leaver)

step() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }
sql()  { sudo -u postgres psql -d "$DB" -tAc "$1"; }

module_state() {
    sql "SELECT COALESCE((SELECT state FROM ir_module_module WHERE name = '$1'), 'absent')"
}

# ---------------------------------------------------------------------------
step "1/6 Pre-checks (read-only)"
[ -f "$TARBALL" ] || fail "tarball $TARBALL not found"
listing=$(tar tzf "$TARBALL") || fail "cannot read $TARBALL"
for m in "${MODULES[@]}"; do
    grep -qx "$m/__manifest__.py" <<< "$listing" \
        || fail "tarball does not contain $m/__manifest__.py"
done
if grep -q $'\r' <(tar xzOf "$TARBALL" xn_activity/__manifest__.py); then
    fail "tarball has CRLF line endings - build it with git -c core.autocrlf=false archive"
fi
for m in "${MODULES[@]}"; do
    sudo test -e "$ADDONS/$m" && fail "$ADDONS/$m already exists - already deployed?"
    state=$(module_state "$m") || fail "cannot query the database (psql as postgres)"
    [ "$state" = "installed" ] && fail "$m is already installed in $DB"
    echo "$m: not on disk, database state '$state'"
done
for m in "${DEPENDS[@]}"; do
    state=$(module_state "$m")
    [ "$state" = "installed" ] || fail "dependency $m is '$state', not installed"
done
echo "Dependencies installed: ${DEPENDS[*]}"
baseurl=$(sql "SELECT value FROM ir_config_parameter WHERE key = 'web.base.url'")
echo "web.base.url: $baseurl (Agent Setup needs https://)"
case "$baseurl" in https://*) ;; *) echo "WARNING: not https - set the server URL in Agent Setup by hand." ;; esac
body=$(sudo nginx -T 2>/dev/null | grep -i client_max_body_size | head -3)
echo "nginx client_max_body_size: ${body:-(not set = 1m default, enough: agent posts are under 100 KB)}"
systemctl is-active --quiet odoo || fail "odoo is not running right now - investigate first"

# ---------------------------------------------------------------------------
step "2/6 Backup (pg_dump + filestore)"
sudo "$BACKUP_SCRIPT" || fail "backup script failed"
status=$(sudo cat "$BACKUP_STATUS")
echo "last_status: $status"
case "$status" in
    OK*) ;;
    *) fail "backup status is not OK" ;;
esac

# ---------------------------------------------------------------------------
step "3/6 Confirm"
echo "Odoo will be stopped for about a minute (users see a 502)."
if [ "${CONFIRM:-}" = "yes" ]; then
    echo "CONFIRM=yes set"
else
    read -r -p "Type yes to continue: " answer
    [ "$answer" = "yes" ] || fail "not confirmed"
fi

# ---------------------------------------------------------------------------
step "4/6 Unpack modules"
sudo tar xzf "$TARBALL" -C "$ADDONS" || fail "tar extract failed"
for m in "${MODULES[@]}"; do
    sudo chown -R auditreelive:auditreelive "$ADDONS/$m"
    sudo ls -ld "$ADDONS/$m"
done

# ---------------------------------------------------------------------------
step "5/6 Stop Odoo, install, start Odoo"
MARK=$(sudo wc -l < "$LOG")
sudo systemctl stop odoo
echo "Odoo stopped at $(date -u +%H:%M:%S) UTC. Installing (output goes to $LOG)..."
sudo -u auditreelive "$PY" "$ODOO_BIN" --config="$CONF" -d "$DB" \
    -i xn_activity --stop-after-init
rc=$?
state=$(module_state xn_activity)
echo "install exit code: $rc, xn_activity state: $state"
echo "--- log lines from this run (errors and load result) ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded|xn_activity" || true
echo "--------------------------------------------------------"

if [ "$state" != "installed" ]; then
    echo "Install did not complete; the database was not changed. Removing the files."
    for m in "${MODULES[@]}"; do sudo rm -rf "${ADDONS:?}/$m"; done
    sudo systemctl start odoo
    sleep 20
    systemctl is-active odoo
    fail "install failed (exit $rc). Odoo is back as it was. Send the log lines above."
fi

if [ "${DIGEST:-off}" != "on" ]; then
    sql "UPDATE ir_cron SET active = false WHERE id = (
           SELECT res_id FROM ir_model_data
            WHERE module = 'xn_activity' AND name = 'cron_xn_activity_digest')" >/dev/null
    echo "Weekly digest cron switched off for the pilot."
fi

sudo systemctl start odoo
echo "Waiting for Odoo to come up..."
sleep 20

# ---------------------------------------------------------------------------
step "6/6 Verify"
systemctl is-active odoo || fail "odoo did not start - run: sudo journalctl -u odoo -n 80"
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/web/login")
echo "GET /web/login -> $code"
[ "$code" = "200" ] || echo "WARNING: expected 200. Retry in a minute; if still not 200, run: sudo journalctl -u odoo -n 80"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
       -d '{}' "$BASE/xn_activity/ingest")
echo "POST /xn_activity/ingest without a key -> $code (expected 403)"
[ "$code" = "403" ] || echo "WARNING: expected 403 - check nginx passes /xn_activity/ to Odoo."

echo "Module states:"
sql "SELECT name || ': ' || state FROM ir_module_module WHERE name IN ('xn_activity','xn_activity_joiner_leaver','xn_joiner_leaver') ORDER BY name"
echo "API key set: $(sql "SELECT CASE WHEN count(*) = 1 THEN 'yes' ELSE 'NO' END FROM ir_config_parameter WHERE key = 'xn_activity.api_key'")"
echo "Apps preloaded: $(sql "SELECT count(*) FROM xn_activity_app")"
echo "Joiner/leaver steps added: $(sql "SELECT count(*) FROM ir_model_data WHERE module = 'xn_activity_joiner_leaver' AND model = 'xn.jl.step'")"
echo "Crons:"
sql "SELECT c.cron_name || '  active=' || c.active || '  next=' || c.nextcall FROM ir_cron c
       JOIN ir_model_data d ON d.res_id = c.id AND d.model = 'ir.cron'
      WHERE d.module = 'xn_activity' ORDER BY c.nextcall"

if [ "$rc" != "0" ]; then
    echo "NOTE: module is installed but the exit code was $rc - send the log lines above."
fi
printf '\nDONE. In the browser (HR Manager): Employees > Activity > Configuration > Agent Setup > Save and Download Installer.\n'
