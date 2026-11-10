#!/usr/bin/env bash
# Replace one file on prod: xn_hr_dashboard/models/hr_employee.py (tile
# click-through actions get a `views` list). Python-only, so Odoo is
# restarted, no -u. Run ON the VM after copying the two versions, built from
# commits:
#
#   git -c core.autocrlf=false show <prod-tag>:custom/addons/xn_hr_dashboard/models/hr_employee.py \
#       > /tmp/hr_employee_old.py
#   git -c core.autocrlf=false show <commit>:custom/addons/xn_hr_dashboard/models/hr_employee.py \
#       > /tmp/hr_employee_new.py
#   gcloud compute scp /tmp/hr_employee_old.py /tmp/hr_employee_new.py \
#       scripts/fix_hr_dashboard_tiles_prod.sh auditreelive-prod-mum:/tmp/ \
#       --tunnel-through-iap --zone=asia-south1-a
#   bash /tmp/fix_hr_dashboard_tiles_prod.sh      (on the VM)
#
# Prod's xn_hr_dashboard has files that match no commit, so only this one
# file is touched, and only if it equals the last prod tag (CRs ignored).
# No database change, so no DB backup; the old file is kept in rollback/.

set -uo pipefail

OLD="${1:-/tmp/hr_employee_old.py}"
NEW="${2:-/tmp/hr_employee_new.py}"
ROOT="/opt/odoo17/auditreelive"
TARGET="$ROOT/custom/addons/xn_hr_dashboard/models/hr_employee.py"
ROLLBACK="$ROOT/rollback"
LOG="/var/log/auditreelive/auditreelive-server.log"
URL="https://odoo.auditree.com/web/login"
TS=$(date -u +%Y%m%d_%H%M%S)

step() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nSTOPPED: %s\n' "$*"; exit 1; }

step "1/4 Pre-checks (read-only)"
for f in "$OLD" "$NEW"; do [ -f "$f" ] || fail "$f not found"; done
grep -q '"views": \[\[False, "list"\], \[False, "form"\]\]' "$NEW" || fail "$NEW is not the fixed version"
grep -q $'\r' "$NEW" && fail "$NEW has CRLF - build it with git -c core.autocrlf=false"
sudo test -f "$TARGET" || fail "$TARGET not found"
if sudo grep -q '"views": \[\[False, "list"\], \[False, "form"\]\]' "$TARGET"; then
    fail "prod already has the fix - nothing to do"
fi
if ! sudo cat "$TARGET" | diff --strip-trailing-cr "$OLD" - ; then
    fail "prod hr_employee.py differs from the last prod tag - not overwriting unknown changes"
fi
echo "Prod file matches the last prod tag."
"$ROOT/venv/bin/python" -m py_compile "$NEW" || fail "new file does not compile"
systemctl is-active --quiet odoo || fail "odoo is not running right now - investigate first"

step "2/4 Swap file (old copy kept)"
sudo mkdir -p "$ROLLBACK"
sudo cp -p "$TARGET" "$ROLLBACK/xn_hr_dashboard_hr_employee_$TS.py"
sudo install -o auditreelive -g auditreelive -m 644 "$NEW" "$TARGET" || fail "copy failed"
echo "Old copy: $ROLLBACK/xn_hr_dashboard_hr_employee_$TS.py"

step "3/4 Restart Odoo (about 20 s of 502)"
MARK=$(sudo wc -l < "$LOG")
sudo systemctl restart odoo
sleep 20

step "4/4 Verify"
if ! systemctl is-active --quiet odoo; then
    echo "Odoo did not come back - restoring the old file."
    sudo install -o auditreelive -g auditreelive -m 644 \
        "$ROLLBACK/xn_hr_dashboard_hr_employee_$TS.py" "$TARGET"
    sudo systemctl restart odoo
    fail "restart failed; old file restored. Run: sudo journalctl -u odoo -n 80"
fi
code=$(curl -s -o /dev/null -w '%{http_code}' "$URL")
echo "odoo: active, GET $URL -> $code"
[ "$code" = "200" ] || echo "WARNING: expected 200. Retry in a minute; else sudo journalctl -u odoo -n 80"
echo "--- new log lines (errors) ---"
sudo tail -n +$((MARK + 1)) "$LOG" | grep -iE "ERROR|CRITICAL|Traceback" || echo "(none)"
printf '\nDONE. Refresh the HR Dashboard and click a tile, e.g. Leave requests waiting on you.\n'
