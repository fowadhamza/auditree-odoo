#!/usr/bin/env bash
# Upgrade xn_activity on the production VM from 17.0.1.7.0 to 17.0.1.8.0:
# connection check for agent 1.3 (connection type, metered flag, Wi-Fi
# signal, response times, speed tests from gs://auditree-agent-speedtest).
# Run ON the VM, with sudo, after copying the tarball and the base
# fingerprint (both built from commits, not the working tree):
#
#   git -c core.autocrlf=false archive --format=tar <commit>:custom/addons \
#       xn_activity | gzip > activity_v18.tar.gz
#   (base fingerprint: the xn_activity tree of f3faf77 = prod-2026-11-19c,
#    one line per file, "<sha256 of content with CRs stripped>  ./<path>",
#    sorted)
#   gcloud compute scp activity_v18.tar.gz activity_v18_base.sha \
#       upgrade_activity_v18_prod.sh \
#       auditreelive-prod-mum:/tmp/ --tunnel-through-iap --zone=asia-south1-a
#   gcloud compute ssh auditreelive-prod-mum --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/upgrade_activity_v18_prod.sh
#
# Stages: pre-checks (incl. drift check) -> backup -> confirm -> swap code ->
# stop / -u / start -> verify. Stops at the first problem. Odoo is down only
# between "stop" and "start" (about a minute). CONFIRM=yes skips the prompt.
#
# Success is judged by exit code + latest_version in the database, never by
# stdout (prod logs to a file; CLAUDE.md s8). If the -u fails, Odoo rolls the
# database back, so the old code is put back too. Sends no email. No
# migration: a new table and new Devices columns; existing data untouched.

set -uo pipefail

TARBALL="${1:-/tmp/activity_v18.tar.gz}"
BASE_SHA="${2:-/tmp/activity_v18_base.sha}"
DB="AUDITREE_LIVE_NEW"
MODULE="xn_activity"
OLD_VERSION="17.0.1.7.0"
NEW_VERSION="17.0.1.8.0"
ADDONS="/opt/odoo17/auditreelive/custom/addons"
# Outside custom/addons: Odoo scans that directory for modules.
OLD_COPY="/opt/odoo17/auditreelive/rollback/${MODULE}_$(date -u +%Y%m%d_%H%M%S)"
LOG="/var/log/auditreelive/auditreelive-server.log"
CONF="/etc/auditreelive-server.conf"
PY="/opt/odoo17/auditreelive/venv/bin/python"
ODOO_BIN="/opt/odoo17/auditreelive/auditreelive-server/odoo-bin"
BACKUP_SCRIPT="/opt/auditree-backup/auditree_backup.sh"
BACKUP_STATUS="/var/backups/auditree/last_status"
BASE="https://odoo.auditree.com"

step() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }
sql()  { sudo -u postgres psql -d "$DB" -tAc "$1"; }
fingerprint() {
    sudo bash -c '
        set -o pipefail
        cd "$1" || exit 1
        find . -type f ! -path "*/__pycache__/*" ! -name "*.pyc" -print0 \
            | LC_ALL=C sort -z \
            | while IFS= read -r -d "" f; do
                  printf "%s  %s\n" "$(tr -d "\r" < "$f" | sha256sum | cut -c1-64)" "$f"
              done' _ "$1"
}

cd /tmp

# ---------------------------------------------------------------------------
step "1/6 Pre-checks (read-only)"
[ -f "$TARBALL" ] || fail "tarball $TARBALL not found"
[ -f "$BASE_SHA" ] || fail "base fingerprint $BASE_SHA not found"
listing=$(tar tzf "$TARBALL") || fail "cannot read $TARBALL"
grep -qx "$MODULE/__manifest__.py" <<< "$listing" || fail "tarball does not contain $MODULE/__manifest__.py"
if grep -q $'\r' <(tar xzOf "$TARBALL" "$MODULE/__manifest__.py"); then
    fail "tarball has CRLF line endings - build it with git -c core.autocrlf=false archive"
fi
grep -q "\"$NEW_VERSION\"" <(tar xzOf "$TARBALL" "$MODULE/__manifest__.py") \
    || fail "tarball manifest is not version $NEW_VERSION"
grep -qx "$MODULE/models/activity_net.py" <<< "$listing" \
    || fail "tarball has no connection check - wrong commit?"
sudo test -d "$ADDONS/$MODULE" || fail "$ADDONS/$MODULE not found on disk"
state=$(sql "SELECT state FROM ir_module_module WHERE name = '$MODULE'") \
    || fail "cannot query the database (psql as postgres)"
version=$(sql "SELECT latest_version FROM ir_module_module WHERE name = '$MODULE'")
echo "$MODULE: state '$state', version '$version'"
[ "$state" = "installed" ] || fail "$MODULE is '$state', expected installed"
[ "$version" = "$OLD_VERSION" ] || fail "$MODULE is at '$version', expected $OLD_VERSION"

echo "Drift check against the base commit..."
prod_fp=$(fingerprint "$ADDONS/$MODULE") || fail "could not fingerprint $ADDONS/$MODULE"
[ -n "$prod_fp" ] || fail "fingerprint of $ADDONS/$MODULE is empty"
echo "Prod files: $(wc -l <<< "$prod_fp")"
if ! diff <(printf '%s\n' "$prod_fp") "$BASE_SHA" > /tmp/activity_v18_drift.txt; then
    cat /tmp/activity_v18_drift.txt
    fail "prod's $MODULE differs from the base commit (diff above, < = prod, > = git). Nothing changed."
fi
echo "Prod code matches the base commit."
systemctl is-active --quiet odoo || fail "odoo is not running right now - investigate first"

# ---------------------------------------------------------------------------
step "2/6 Backup (pg_dump + filestore)"
sudo "$BACKUP_SCRIPT" || fail "backup script failed"
status=$(sudo cat "$BACKUP_STATUS")
echo "last_status: $status"
case "$status" in OK*) ;; *) fail "backup status is not OK" ;; esac

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
step "4/6 Swap code (old copy kept at $OLD_COPY)"
sudo mkdir -p "$(dirname "$OLD_COPY")"
sudo mv "$ADDONS/$MODULE" "$OLD_COPY" || fail "could not move the old module aside"
if ! sudo tar xzf "$TARBALL" -C "$ADDONS"; then
    sudo rm -rf "${ADDONS:?}/$MODULE"; sudo mv "$OLD_COPY" "$ADDONS/$MODULE"
    fail "tar extract failed; old code put back"
fi
sudo chown -R auditreelive:auditreelive "$ADDONS/$MODULE"
sudo ls -ld "$ADDONS/$MODULE"

restore_old_code() {
    sudo rm -rf "${ADDONS:?}/$MODULE"
    sudo mv "$OLD_COPY" "$ADDONS/$MODULE"
}

# ---------------------------------------------------------------------------
step "5/6 Stop Odoo, upgrade, start Odoo"
MARK=$(sudo wc -l < "$LOG")
sudo systemctl stop odoo
echo "Odoo stopped at $(date -u +%H:%M:%S) UTC. Upgrading (output goes to $LOG)..."
sudo -u auditreelive "$PY" "$ODOO_BIN" --config="$CONF" -d "$DB" \
    -u "$MODULE" --stop-after-init
rc=$?
version=$(sql "SELECT latest_version FROM ir_module_module WHERE name = '$MODULE'")
echo "upgrade exit code: $rc, $MODULE version now: $version"
echo "--- log lines from this run (errors and load result) ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded|$MODULE" || true
echo "--------------------------------------------------------"

if [ "$version" != "$NEW_VERSION" ]; then
    echo "Upgrade did not complete; the database is still at $version. Putting the old code back."
    restore_old_code
    sudo systemctl start odoo
    sleep 20
    systemctl is-active odoo
    fail "upgrade failed (exit $rc). Odoo is back as it was. Send the log lines above."
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
echo "Work Accounts Only (unchanged): '$(sql "SELECT coalesce(max(value), '') FROM ir_config_parameter
       WHERE key = 'xn_activity.work_accounts_only'")'"
echo "Connection table: $(sql "SELECT count(*) FROM information_schema.tables
       WHERE table_name = 'xn_activity_net'") (expected 1)"
echo "New Devices columns: $(sql "SELECT count(*) FROM information_schema.columns
       WHERE table_name = 'xn_activity_device' AND column_name LIKE 'net%'") (expected 7)"
code=$(curl -s -o /dev/null -w '%{http_code}' \
       "https://storage.googleapis.com/auditree-agent-speedtest/speedtest-2mb.bin")
echo "Speed test file from the VM -> $code (expected 200)"
echo "Day rows / slots: $(sql "SELECT count(*) FROM xn_activity_day") / $(sql "SELECT count(*) FROM xn_activity_slot")"
if [ "$rc" != "0" ]; then
    echo "NOTE: the version moved but the exit code was $rc - send the log lines above."
fi
printf '\nDONE. Old code kept at %s (delete after a few days).\n' "$OLD_COPY"
printf 'Next: hard-refresh; Agent Setup shows Connection Check; download the agent 1.3 installer for IT.\n'
