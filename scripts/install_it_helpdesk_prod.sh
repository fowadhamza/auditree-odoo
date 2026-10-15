#!/usr/bin/env bash
# Install the IT Helpdesk (helpdesk_mgmt + xn_it_helpdesk) on the production VM
# as a trial. Run ON the VM, as a user with sudo, after copying the tarball:
#
#   tar czf /tmp/helpdesk.tar.gz -C custom/addons --exclude=__pycache__ \
#       --exclude='*.pyc' helpdesk_mgmt xn_it_helpdesk
#   gcloud compute scp /tmp/helpdesk.tar.gz scripts/install_it_helpdesk_prod.sh \
#       auditreelive-prod-mum:/tmp/ --tunnel-through-iap --zone=asia-south1-a
#   gcloud compute ssh auditreelive-prod-mum --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/install_it_helpdesk_prod.sh /tmp/helpdesk.tar.gz
#
# Stages: pre-checks -> backup -> confirm -> unpack -> stop / install / start
# -> verify. It stops at the first problem. Odoo is down only between "stop"
# and "start" (about a minute).
#
# Success is judged by the exit code and the module state in the database,
# never by stdout: prod logs to a file, so stdout is empty (CLAUDE.md s8).
# Files are only removed again when the database says the module is NOT
# installed, so code and database can never end up out of step.

set -uo pipefail

TARBALL="${1:-/tmp/helpdesk.tar.gz}"
DB="AUDITREE_LIVE_NEW"
ADDONS="/opt/odoo17/auditreelive/custom/addons"
LOG="/var/log/auditreelive/auditreelive-server.log"
CONF="/etc/auditreelive-server.conf"
PY="/opt/odoo17/auditreelive/venv/bin/python"
ODOO_BIN="/opt/odoo17/auditreelive/auditreelive-server/odoo-bin"
BACKUP_SCRIPT="/opt/auditree-backup/auditree_backup.sh"
BACKUP_STATUS="/var/backups/auditree/last_status"
URL="https://odoo.auditree.com/web/login"
MODULES=(helpdesk_mgmt xn_it_helpdesk)
LOGINS="'it@auditree.com','junaid.k@auditree.com','ayesha.siddiqua@auditree.com'"

step() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }
sql()  { sudo -u postgres psql -d "$DB" -tAc "$1"; }

module_state() {
    sql "SELECT COALESCE((SELECT state FROM ir_module_module WHERE name = '$1'), 'absent')"
}

# ---------------------------------------------------------------------------
step "1/6 Pre-checks (read-only)"
[ -f "$TARBALL" ] || fail "tarball $TARBALL not found"
# List once into a variable: "tar | grep -q" can trip pipefail via SIGPIPE.
listing=$(tar tzf "$TARBALL") || fail "cannot read $TARBALL"
for m in "${MODULES[@]}"; do
    grep -qx "$m/__manifest__.py" <<< "$listing" \
        || fail "tarball does not contain $m/__manifest__.py"
done
for m in "${MODULES[@]}"; do
    sudo test -e "$ADDONS/$m" && fail "$ADDONS/$m already exists - already deployed?"
    state=$(module_state "$m") || fail "cannot query the database (psql as postgres)"
    [ "$state" = "installed" ] && fail "$m is already installed in $DB"
    echo "$m: not on disk, database state '$state'"
done
echo "Users that will get access:"
sql "SELECT login || '  active=' || active FROM res_users WHERE login IN ($LOGINS) ORDER BY login"
found=$(sql "SELECT count(*) FROM res_users WHERE login IN ($LOGINS) AND active")
[ "$found" = "3" ] || echo "WARNING: only $found of 3 logins exist and are active; missing ones are skipped."
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
read -r -p "Type yes to continue: " answer
[ "$answer" = "yes" ] || fail "not confirmed"

# ---------------------------------------------------------------------------
step "4/6 Unpack modules"
sudo tar xzf "$TARBALL" -C "$ADDONS" || fail "tar extract failed"
for m in "${MODULES[@]}"; do
    sudo chown -R auditreelive:auditreelive "$ADDONS/$m"
done
sudo ls -ld "$ADDONS/helpdesk_mgmt" "$ADDONS/xn_it_helpdesk"

# ---------------------------------------------------------------------------
step "5/6 Stop Odoo, install, start Odoo"
MARK=$(sudo wc -l < "$LOG")
sudo systemctl stop odoo
echo "Odoo stopped at $(date -u +%H:%M:%S) UTC. Installing (output goes to $LOG)..."
sudo -u auditreelive "$PY" "$ODOO_BIN" --config="$CONF" -d "$DB" \
    -i xn_it_helpdesk --stop-after-init
rc=$?
state=$(module_state xn_it_helpdesk)
echo "install exit code: $rc, xn_it_helpdesk state: $state"
echo "--- log lines from this run (errors and load result) ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded" || true
echo "--------------------------------------------------------"

if [ "$state" != "installed" ]; then
    echo "Install did not complete; the database was not changed. Removing the files."
    for m in "${MODULES[@]}"; do sudo rm -rf "${ADDONS:?}/$m"; done
    sudo systemctl start odoo
    sleep 20
    systemctl is-active odoo
    fail "install failed (exit $rc). Odoo is back as it was. Send the log lines above."
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

echo "Module states:"
sql "SELECT name || ': ' || state FROM ir_module_module WHERE name IN ('helpdesk_mgmt','xn_it_helpdesk') ORDER BY name"
echo "Raise IT Tickets group members:"
sql "SELECT u.login FROM res_groups_users_rel r
       JOIN res_users u ON u.id = r.uid
       JOIN ir_model_data d ON d.res_id = r.gid AND d.model = 'res.groups'
      WHERE d.module = 'xn_it_helpdesk' AND d.name = 'group_xn_helpdesk_requester'
      ORDER BY u.login"
echo "IT Support team members:"
sql "SELECT u.login FROM helpdesk_ticket_team_res_users_rel r
       JOIN res_users u ON u.id = r.res_users_id
       JOIN ir_model_data d ON d.res_id = r.helpdesk_ticket_team_id AND d.model = 'helpdesk.ticket.team'
      WHERE d.module = 'xn_it_helpdesk' AND d.name = 'team_it_support'
      ORDER BY u.login"

if [ "$rc" != "0" ]; then
    echo "NOTE: module is installed but the exit code was $rc - send the log lines above."
fi
printf '\nDONE. Check in the browser: Administrator and it@ see IT Helpdesk; other staff do not.\n'
