#!/usr/bin/env bash
# Upgrade xn_joiner_leaver on the production VM to 17.0.1.2.0: My Steps shows
# only the user's own steps, and the step form gets an Attach Proof upload.
# Run ON the VM, as a user with sudo, after copying the tarball and the base
# fingerprint (both built from commits, not the working tree):
#
#   git -c core.autocrlf=false archive --format=tar <commit>:custom/addons \
#       xn_joiner_leaver | gzip > jl_v12.tar.gz
#   (base fingerprint: the xn_joiner_leaver tree of the last prod tag, one line
#    per file, "<sha256 of content with CRs stripped>  ./<path>", sorted)
#   gcloud compute scp jl_v12.tar.gz jl_base.sha upgrade_joiner_leaver_v12_prod.sh \
#       auditreelive-prod-mum:/tmp/ --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/upgrade_joiner_leaver_v12_prod.sh
#
# Stages: pre-checks (incl. drift check) -> backup -> confirm -> swap code ->
# stop / -u / start -> verify. Stops at the first problem. CONFIRM=yes skips
# the prompt. Success is judged by exit code + latest_version, never stdout.
# If the -u fails the old code is put back. Sends no email.

set -uo pipefail

TARBALL="${1:-/tmp/jl_v12.tar.gz}"
BASE_SHA="${2:-/tmp/jl_base.sha}"
DB="AUDITREE_LIVE_NEW"
MODULE="xn_joiner_leaver"
OLD_VERSION="17.0.1.1.0"
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
if ! diff <(printf '%s\n' "$prod_fp") "$BASE_SHA" > /tmp/jl_v12_drift.txt; then
    cat /tmp/jl_v12_drift.txt
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
echo "My Steps action domain: $(sql "SELECT a.domain FROM ir_act_window a JOIN ir_model_data d ON d.res_id = a.id AND d.model = 'ir.actions.act_window' WHERE d.module = '$MODULE' AND d.name = 'action_xn_jl_my_tasks'")"
echo "Step form has Attach Proof: $(sql "SELECT count(*) FROM ir_ui_view v JOIN ir_model_data d ON d.res_id = v.id AND d.model = 'ir.ui.view' WHERE d.module = '$MODULE' AND d.name = 'view_task_form_xn_jl_step' AND v.arch_db::text LIKE '%xn_jl_proof_ids%'") (expected 1)"
if [ "$rc" != "0" ]; then
    echo "NOTE: the version moved but the exit code was $rc - send the log lines above."
fi
printf '\nDONE. Old code kept at %s (delete after a few days).\n' "$OLD_COPY"
