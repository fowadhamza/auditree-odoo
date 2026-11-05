#!/usr/bin/env bash
# Install the joiner/leaver checklists (xn_joiner_leaver, plus
# xn_joiner_leaver_helpdesk, which installs itself when xn_it_helpdesk is
# installed) on the production VM. Run ON the VM, as a user with sudo, after
# copying the tarball (built from a commit, not the working tree):
#
#   git -c core.autocrlf=false archive --format=tar <commit>:custom/addons \
#       xn_joiner_leaver xn_joiner_leaver_helpdesk | gzip > /tmp/joiner_leaver.tar.gz
#   gcloud compute scp /tmp/joiner_leaver.tar.gz scripts/install_joiner_leaver_prod.sh \
#       auditreelive-prod-mum:/tmp/ --tunnel-through-iap --zone=asia-south1-a
#   gcloud compute ssh auditreelive-prod-mum --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/install_joiner_leaver_prod.sh /tmp/joiner_leaver.tar.gz
#
# Stages: pre-checks -> backup -> confirm -> unpack -> stop / install / start
# -> verify. It stops at the first problem. Odoo is down only between "stop"
# and "start" (about a minute). CONFIRM=yes skips the prompt.
#
# Success is judged by the exit code and the module state in the database,
# never by stdout: prod logs to a file, so stdout is empty (CLAUDE.md s8).
# Files are only removed again when the database says the module is NOT
# installed, so code and database can never end up out of step.
#
# Installing sends no email. The daily digest starts emailing once HR starts
# a checklist or approves a resignation.

set -uo pipefail

TARBALL="${1:-/tmp/joiner_leaver.tar.gz}"
DB="AUDITREE_LIVE_NEW"
ADDONS="/opt/odoo17/auditreelive/custom/addons"
LOG="/var/log/auditreelive/auditreelive-server.log"
CONF="/etc/auditreelive-server.conf"
PY="/opt/odoo17/auditreelive/venv/bin/python"
ODOO_BIN="/opt/odoo17/auditreelive/auditreelive-server/odoo-bin"
BACKUP_SCRIPT="/opt/auditree-backup/auditree_backup.sh"
BACKUP_STATUS="/var/backups/auditree/last_status"
URL="https://odoo.auditree.com/web/login"
MODULES=(xn_joiner_leaver xn_joiner_leaver_helpdesk)
DEPENDS=(hr project mail resource hr_resignation)
# Role holders (ROLE_LOGINS in xn_joiner_leaver/__init__.py).
LOGINS="'shaik.danyal@auditree.com','sharook.mohamed@auditree.com','ghazala.nishath@auditree.com','ayesha.siddiqua@auditree.com','it@auditree.com','mohammed.junaid@auditree.com'"

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
if grep -q $'\r' <(tar xzOf "$TARBALL" xn_joiner_leaver/__manifest__.py); then
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
helpdesk=$(module_state xn_it_helpdesk)
echo "xn_it_helpdesk: $helpdesk (installed -> xn_joiner_leaver_helpdesk installs itself)"
echo "Role holders (get Project > User if they lack it):"
sql "SELECT login || '  active=' || active FROM res_users WHERE login IN ($LOGINS) ORDER BY login"
found=$(sql "SELECT count(*) FROM res_users WHERE login IN ($LOGINS) AND active")
[ "$found" = "6" ] || echo "WARNING: only $found of 6 logins exist and are active; missing roles are left empty."
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
    -i xn_joiner_leaver --stop-after-init
rc=$?
state=$(module_state xn_joiner_leaver)
echo "install exit code: $rc, xn_joiner_leaver state: $state"
echo "--- log lines from this run (errors and load result) ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback|Modules loaded|xn_joiner_leaver" || true
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
sql "SELECT name || ': ' || state FROM ir_module_module WHERE name IN ('xn_joiner_leaver','xn_joiner_leaver_helpdesk','xn_it_helpdesk') ORDER BY name"
echo "Roles:"
sql "SELECT r.code || ' -> ' || COALESCE(u.login, '(empty)') FROM xn_jl_role r LEFT JOIN res_users u ON u.id = r.user_id ORDER BY r.sequence"
echo "Steps: $(sql "SELECT process || '=' || count(*) FROM xn_jl_step GROUP BY process ORDER BY process" | tr '\n' ' ')"
echo "Crons:"
sql "SELECT c.cron_name || '  active=' || c.active || '  next=' || c.nextcall FROM ir_cron c
       JOIN ir_model_data d ON d.res_id = c.id AND d.model = 'ir.cron'
      WHERE d.module = 'xn_joiner_leaver' ORDER BY c.nextcall"

if [ "$rc" != "0" ]; then
    echo "NOTE: module is installed but the exit code was $rc - send the log lines above."
fi
printf '\nDONE. Check in the browser: HR sees Joiners and Leavers; Start Joining Checklist on an employee opens a dialog.\n'
