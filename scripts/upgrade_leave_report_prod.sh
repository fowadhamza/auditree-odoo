#!/usr/bin/env bash
# Upgrade xn_hr_leave_report on the production VM (frozen Employee column,
# 17.0.3.0.2 -> 17.0.3.0.3). Run ON the VM, as a user with sudo, after
# copying two tarballs built from commits, not the working tree:
#
#   git -c core.autocrlf=false archive --format=tar <prod-tag>:custom/addons \
#       xn_hr_leave_report | gzip > /tmp/leave_report_old.tar.gz
#   git -c core.autocrlf=false archive --format=tar <commit>:custom/addons \
#       xn_hr_leave_report | gzip > /tmp/leave_report_new.tar.gz
#   gcloud compute scp /tmp/leave_report_old.tar.gz /tmp/leave_report_new.tar.gz \
#       scripts/upgrade_leave_report_prod.sh auditreelive-prod-mum:/tmp/ \
#       --tunnel-through-iap --zone=asia-south1-a
#   gcloud compute ssh auditreelive-prod-mum --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/upgrade_leave_report_prod.sh
#
# Stages: pre-checks -> backup -> confirm -> swap -> stop / -u / start ->
# verify. Stops at the first problem. The old module directory is kept in
# rollback/ (outside custom/addons). Success is judged by exit code + module
# version in the database, never by stdout (prod logs to a file).

set -uo pipefail

OLD_TAR="${1:-/tmp/leave_report_old.tar.gz}"
NEW_TAR="${2:-/tmp/leave_report_new.tar.gz}"
MODULE="xn_hr_leave_report"
NEW_VERSION="17.0.3.0.3"
DB="AUDITREE_LIVE_NEW"
ROOT="/opt/odoo17/auditreelive"
ADDONS="$ROOT/custom/addons"
ROLLBACK="$ROOT/rollback"
LOG="/var/log/auditreelive/auditreelive-server.log"
CONF="/etc/auditreelive-server.conf"
PY="$ROOT/venv/bin/python"
ODOO_BIN="$ROOT/auditreelive-server/odoo-bin"
BACKUP_SCRIPT="/opt/auditree-backup/auditree_backup.sh"
BACKUP_STATUS="/var/backups/auditree/last_status"
URL="https://odoo.auditree.com/web/login"
TS=$(date -u +%Y%m%d_%H%M%S)
WORK=$(mktemp -d)

step() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }
sql()  { sudo -u postgres psql -d "$DB" -tAc "$1"; }
mod()  { sql "SELECT state || ' ' || COALESCE(latest_version, '') FROM ir_module_module WHERE name = '$MODULE'"; }

# ---------------------------------------------------------------------------
step "1/6 Pre-checks (read-only)"
for t in "$OLD_TAR" "$NEW_TAR"; do [ -f "$t" ] || fail "$t not found"; done
mkdir -p "$WORK/old" "$WORK/new"
tar xzf "$OLD_TAR" -C "$WORK/old" || fail "cannot read $OLD_TAR"
tar xzf "$NEW_TAR" -C "$WORK/new" || fail "cannot read $NEW_TAR"
[ -f "$WORK/new/$MODULE/__manifest__.py" ] || fail "new tarball lacks $MODULE/__manifest__.py"
grep -q $'\r' "$WORK/new/$MODULE/__manifest__.py" && fail "new tarball has CRLF - use git -c core.autocrlf=false archive"
grep -q "'$NEW_VERSION'" "$WORK/new/$MODULE/__manifest__.py" || fail "new tarball is not version $NEW_VERSION"
sudo test -d "$ADDONS/$MODULE" || fail "$ADDONS/$MODULE not on disk"
echo "DB: $(mod)"
# Drift check: prod files must equal the last prod tag (CRs ignored).
sudo cp -r "$ADDONS/$MODULE" "$WORK/live"
sudo chown -R "$(id -u)" "$WORK/live"
if ! diff -r --strip-trailing-cr -x __pycache__ -x '*.pyc' "$WORK/old/$MODULE" "$WORK/live" > "$WORK/drift.txt"; then
    cat "$WORK/drift.txt"
    fail "prod $MODULE differs from the last prod tag - not overwriting unknown changes"
fi
echo "Prod files match the last prod tag."
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
if [ "${CONFIRM:-}" = "yes" ]; then echo "CONFIRM=yes set"; else
    read -r -p "Type yes to continue: " answer
    [ "$answer" = "yes" ] || fail "not confirmed"
fi

# ---------------------------------------------------------------------------
step "4/6 Swap module directory"
sudo mkdir -p "$ROLLBACK"
sudo mv "$ADDONS/$MODULE" "$ROLLBACK/${MODULE}_$TS" || fail "could not move old module aside"
sudo cp -r "$WORK/new/$MODULE" "$ADDONS/$MODULE"
sudo chown -R auditreelive:auditreelive "$ADDONS/$MODULE"
echo "Old copy: $ROLLBACK/${MODULE}_$TS"

restore_old() {
    sudo rm -rf "${ADDONS:?}/$MODULE"
    sudo mv "$ROLLBACK/${MODULE}_$TS" "$ADDONS/$MODULE"
}

# ---------------------------------------------------------------------------
step "5/6 Stop Odoo, upgrade, start Odoo"
MARK=$(sudo wc -l < "$LOG")
sudo systemctl stop odoo
echo "Odoo stopped at $(date -u +%H:%M:%S) UTC. Upgrading (output goes to $LOG)..."
sudo -u auditreelive "$PY" "$ODOO_BIN" --config="$CONF" -d "$DB" -u "$MODULE" --stop-after-init
rc=$?
after=$(mod)
echo "upgrade exit code: $rc, DB: $after"
echo "--- log lines from this run ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded|$MODULE" || true
echo "-------------------------------"

if [ "$rc" != "0" ] || [ "$after" != "installed $NEW_VERSION" ]; then
    if [ "$after" != "installed $NEW_VERSION" ]; then
        echo "Database not at $NEW_VERSION; restoring the old files."
        restore_old
    fi
    sudo systemctl start odoo
    sleep 20
    systemctl is-active odoo
    fail "upgrade problem (exit $rc, DB '$after'). Send the log lines above."
fi

sudo systemctl start odoo
echo "Waiting for Odoo to come up..."
sleep 20

# ---------------------------------------------------------------------------
step "6/6 Verify"
systemctl is-active odoo || fail "odoo did not start - run: sudo journalctl -u odoo -n 80"
code=$(curl -s -o /dev/null -w '%{http_code}' "$URL")
echo "GET $URL -> $code"
[ "$code" = "200" ] || echo "WARNING: expected 200. Retry in a minute; else sudo journalctl -u odoo -n 80"
echo "Tree class in DB: $(sql "SELECT count(*) FROM ir_ui_view WHERE model LIKE 'hr.leave.%' AND arch_db::text LIKE '%xn_freeze_name%'") views (expect 3)"
rm -rf "$WORK"
printf '\nDONE. Hard-refresh Time Off > Employee Leave Balances and scroll right.\n'
