#!/usr/bin/env bash
# Upgrade xn_it_helpdesk on the production VM to 17.0.1.2.0 (management
# approval on IT tickets). Run ON the VM, as a user with sudo, after copying
# the tarball and the base fingerprint (both built from commits, not the
# working tree):
#
#   git -c core.autocrlf=false archive --format=tar <commit>:custom/addons \
#       xn_it_helpdesk | gzip > /tmp/it_helpdesk_approval.tar.gz
#   (base fingerprint of 3d7d80e: see the deploy notes / commit message)
#   gcloud compute scp /tmp/it_helpdesk_approval.tar.gz /tmp/it_helpdesk_base.sha \
#       scripts/upgrade_it_helpdesk_approval_prod.sh \
#       auditreelive-prod-mum:/tmp/ --tunnel-through-iap --zone=asia-south1-a
#   gcloud compute ssh auditreelive-prod-mum --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/upgrade_it_helpdesk_approval_prod.sh
#
# Stages: pre-checks (incl. drift check) -> backup -> confirm -> swap code ->
# stop / -u / start -> verify. It stops at the first problem. Odoo is down
# only between "stop" and "start" (about a minute). CONFIRM=yes skips the
# prompt.
#
# Drift check: prod's current xn_it_helpdesk must match the commit this
# change was built on (3d7d80e), compared with CRs stripped. If prod carries
# changes that are not in git, the upgrade would silently drop them, so the
# script stops instead.
#
# Success is judged by exit code + latest_version in the database, never by
# stdout (prod logs to a file; CLAUDE.md s8). If the -u fails, Odoo rolls
# the database back, so the old code is put back too.
#
# Upgrading sends no email. Approval emails start when IT first clicks
# Request Approval.

set -uo pipefail

TARBALL="${1:-/tmp/it_helpdesk_approval.tar.gz}"
BASE_SHA="${2:-/tmp/it_helpdesk_base.sha}"
DB="AUDITREE_LIVE_NEW"
MODULE="xn_it_helpdesk"
NEW_VERSION="17.0.1.2.0"
ADDONS="/opt/odoo17/auditreelive/custom/addons"
# Outside custom/addons: Odoo scans that directory for modules.
OLD_COPY="/opt/odoo17/auditreelive/module_backups/${MODULE}_$(date -u +%Y%m%d_%H%M%S)"
LOG="/var/log/auditreelive/auditreelive-server.log"
CONF="/etc/auditreelive-server.conf"
PY="/opt/odoo17/auditreelive/venv/bin/python"
ODOO_BIN="/opt/odoo17/auditreelive/auditreelive-server/odoo-bin"
BACKUP_SCRIPT="/opt/auditree-backup/auditree_backup.sh"
BACKUP_STATUS="/var/backups/auditree/last_status"
URL="https://odoo.auditree.com/web/login"
APPROVER_LOGIN="ghazala.nishath@auditree.com"

step() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }
sql()  { sudo -u postgres psql -d "$DB" -tAc "$1"; }
fingerprint() {
    # One line per file: sha256 of the content with CRs stripped, then path.
    # All of it as root: the addons tree is not readable by login users, so
    # even the cd must be inside sudo. Fails loudly if the directory is
    # unreadable instead of printing an empty list.
    sudo bash -c '
        set -o pipefail
        cd "$1" || exit 1
        find . -type f ! -path "*/__pycache__/*" ! -name "*.pyc" -print0 \
            | LC_ALL=C sort -z \
            | while IFS= read -r -d "" f; do
                  printf "%s  %s\n" "$(tr -d "\r" < "$f" | sha256sum | cut -c1-64)" "$f"
              done' _ "$1"
}

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
sudo test -d "$ADDONS/$MODULE" || fail "$ADDONS/$MODULE not found on disk"
state=$(sql "SELECT state FROM ir_module_module WHERE name = '$MODULE'") \
    || fail "cannot query the database (psql as postgres)"
version=$(sql "SELECT latest_version FROM ir_module_module WHERE name = '$MODULE'")
echo "$MODULE: state '$state', version '$version'"
[ "$state" = "installed" ] || fail "$MODULE is '$state', expected installed"
[ "$version" = "17.0.1.1.0" ] || fail "$MODULE is at '$version', expected 17.0.1.1.0"

echo "Drift check against the base commit..."
prod_fp=$(fingerprint "$ADDONS/$MODULE") || fail "could not fingerprint $ADDONS/$MODULE"
[ -n "$prod_fp" ] || fail "fingerprint of $ADDONS/$MODULE is empty"
echo "Prod files: $(wc -l <<< "$prod_fp")"
if ! diff <(printf '%s\n' "$prod_fp") "$BASE_SHA" > /tmp/it_helpdesk_drift.txt; then
    cat /tmp/it_helpdesk_drift.txt
    fail "prod's $MODULE differs from the base commit (diff above, < = prod, > = git). Nothing changed. Reconcile first."
fi
echo "Prod code matches the base commit."
approver=$(sql "SELECT count(*) FROM res_users WHERE login = '$APPROVER_LOGIN' AND active")
[ "$approver" = "1" ] && echo "Default approver $APPROVER_LOGIN exists." \
    || echo "WARNING: $APPROVER_LOGIN not found/active; set the Default Approver on the IT Support team by hand."
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
echo "--- log lines from this run (errors, migration, load result) ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded|migration|$MODULE" || true
echo "----------------------------------------------------------------"

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
code=$(curl -s -o /dev/null -w '%{http_code}' "$URL")
echo "GET $URL -> $code"
[ "$code" = "200" ] || echo "WARNING: expected 200. Retry in a minute; if still not 200, run: sudo journalctl -u odoo -n 80"
echo "Stages:"
sql "SELECT sequence || '  ' || name->>'en_US' || '  (' || COALESCE(xn_state, '-') || ')' FROM helpdesk_ticket_stage WHERE active ORDER BY sequence, id"
echo "IT Support default approver:"
sql "SELECT COALESCE(u.login, '(none)') FROM helpdesk_ticket_team t
       JOIN ir_model_data d ON d.res_id = t.id AND d.model = 'helpdesk.ticket.team'
                           AND d.module = '$MODULE' AND d.name = 'team_it_support'
       LEFT JOIN res_users u ON u.id = t.xn_default_approver_id"
if [ "$rc" != "0" ]; then
    echo "NOTE: the version moved but the exit code was $rc - send the log lines above."
fi
printf '\nDONE. Old code kept at %s (delete after a few days).\n' "$OLD_COPY"
printf 'Check in the browser: an IT user sees Request Approval on an open ticket; IT Helpdesk shows To Approve.\n'
