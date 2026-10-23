#!/usr/bin/env bash
# Pack this dev environment into an encrypted, split bundle for a new laptop.
#
# What goes in:
#   - the whole Auditree working tree incl. .git (uncommitted work, unpushed
#     branches, untracked files such as local-dev.conf, start-local.sh, deploy/
#     scripts and deploy/secrets/prod.env)
#   - a fresh pg_dump of the local AUDITREE_LIVE_NEW database + its filestore
#   - ~/.ssh (GitHub, DigitalOcean, GCP keys) and ~/.gitconfig
#   - the Claude Code memory folder for this project (Windows side)
#   - the Odoo core commit + any local diff (core itself is re-cloned on unpack)
#
# What stays out (reproducible or already in GCS): venv/, auditreelive-server/,
# the root *.tar.gz / *.dump backups, the stray "-C" archive, logs, and the dated
# prod-data copies under deploy/{migration-work,do-sync,gcp-backup}.
#
# Usage (WSL terminal, any directory):
#   bash scripts/laptop-migration/pack.sh [OUT_DIR]      # default ~/auditree-migration
# Env:
#   INCLUDE_PROD_DATA_COPIES=1   also pack the dated deploy/ data folders (~340 MB)
#   PART_SIZE=90m                split size; GitHub rejects files over 100 MB
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")/../.." && pwd)"
PNAME="$(basename "$PROJECT")"
OUT_DIR="${1:-$HOME/auditree-migration}"
PART_SIZE="${PART_SIZE:-90m}"
CONF="$PROJECT/local-dev.conf"
DB_NAME="$(sed -n 's/^db_name *= *//p' "$CONF")"
DB_USER="$(sed -n 's/^db_user *= *//p' "$CONF")"
FILESTORE_ROOT="$HOME/.local/share/Odoo"
CLAUDE_MEM="/mnt/c/Users/FowadHamza/.claude/projects/--wsl-localhost-Ubuntu-24-04-home-fowadhamza-Projects-Auditree/memory"

command -v gpg >/dev/null || { echo "gpg missing: sudo apt install -y gnupg"; exit 1; }
if [ -e "$OUT_DIR" ] && [ -n "$(ls -A "$OUT_DIR" 2>/dev/null)" ]; then
    echo "$OUT_DIR is not empty -- move it away first"; exit 1
fi

read -r -s -p "Bundle passphrase (min 16 chars): " PASS; echo
[ "${#PASS}" -ge 16 ] || { echo "Too short"; exit 1; }
read -r -s -p "Repeat passphrase: " PASS2; echo
[ "$PASS" = "$PASS2" ] || { echo "Passphrases differ"; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
META="$STAGE/migration-meta"
mkdir -p "$OUT_DIR" "$META"

echo "== 1/4 database dump ($DB_NAME)"
pg_isready -q || sudo service postgresql start
pg_dump -U "$DB_USER" -Fc -d "$DB_NAME" -f "$META/$DB_NAME.dump"
ls -lh "$META/$DB_NAME.dump"

echo "== 2/4 metadata"
CORE="$PROJECT/auditreelive-server"
git -C "$CORE" rev-parse HEAD > "$META/odoo-core.commit"
git -C "$CORE" diff --binary HEAD > "$META/odoo-core.diff"
git -C "$CORE" status --porcelain --untracked-files=normal > "$META/odoo-core.status" || true
# files on disk that git does not track (newer upstream modules etc.);
# OLD-addons/ is a stale backup copy Odoo never loads, so it stays behind
git -C "$CORE" ls-files -z --others --exclude-standard -- . ':!OLD-addons' \
  | tar -C "$CORE" --null -T - -czf "$META/odoo-core-untracked.tgz"
echo "   core: $(wc -l < "$META/odoo-core.diff") diff lines, $(tar -tzf "$META/odoo-core-untracked.tgz" | wc -l) untracked files"
python3 --version > "$META/versions.txt" 2>&1
psql --version >> "$META/versions.txt" 2>&1
python3 -m pip freeze > "$META/pip-freeze-system.txt" 2>/dev/null || true
[ -x "$PROJECT/venv/bin/pip" ] && "$PROJECT/venv/bin/pip" freeze > "$META/pip-freeze-venv.txt" || true
apt-mark showmanual > "$META/apt-manual.txt" 2>/dev/null || true
echo "$DB_NAME" > "$META/db_name"
echo "$HOME" > "$META/old_home"
if [ -d "$CLAUDE_MEM" ]; then
    cp -r "$CLAUDE_MEM" "$META/claude-memory"
else
    echo "   (Claude memory folder not found at $CLAUDE_MEM -- skipped)"
fi
if [ -s "$META/odoo-core.diff" ]; then
    echo "   NOTE: Odoo core has local changes -- saved to odoo-core.diff"
fi

echo "== 3/4 exclude list"
EXCL="$STAGE/excludes"
cat > "$EXCL" <<EOF
$PNAME/venv
$PNAME/auditreelive-server
$PNAME/auditreelive-server.tar.gz
$PNAME/AUDITREE_ADDONS.tar.gz
$PNAME/AUDITREE_FILESTORE.tar.gz
$PNAME/AUDITREE_LIVE_NEW.dump
$PNAME/-C
$PNAME/*.log
$PNAME/odoo-local.pid
*/__pycache__
*.pyc
*Zone.Identifier
EOF
if [ "${INCLUDE_PROD_DATA_COPIES:-0}" != "1" ]; then
    cat >> "$EXCL" <<EOF
$PNAME/deploy/migration-work/upload_*
$PNAME/deploy/migration-work/bk-test*
$PNAME/deploy/do-sync/2026*
$PNAME/deploy/gcp-backup/*
$PNAME/deploy/__pycache__
EOF
fi

echo "== 4/4 tar | gpg (AES256) | split $PART_SIZE  -> $OUT_DIR"
SRC=( -C "$STAGE" migration-meta -C "$(dirname "$PROJECT")" "$PNAME" -C "$HOME" .ssh )
if [ -f "$HOME/.gitconfig" ]; then SRC+=( -C "$HOME" .gitconfig ); fi
if [ -d "$FILESTORE_ROOT/filestore/$DB_NAME" ]; then
    SRC+=( -C "$FILESTORE_ROOT" "filestore/$DB_NAME" )
else
    echo "   WARNING: no filestore at $FILESTORE_ROOT/filestore/$DB_NAME"
fi

tar --exclude-from="$EXCL" -czf - "${SRC[@]}" \
  | gpg --batch --yes --pinentry-mode loopback --passphrase-fd 3 \
        --symmetric --cipher-algo AES256 --s2k-digest-algo SHA512 \
        --s2k-mode 3 --s2k-count 65011712 -o - 3<<<"$PASS" \
  | split -b "$PART_SIZE" -d -a 3 - "$OUT_DIR/auditree-bundle.tgz.gpg.part-"

cp "$PROJECT/scripts/laptop-migration/unpack.sh" "$PROJECT/scripts/laptop-migration/README.md" \
   "$PROJECT/scripts/laptop-migration/NEW-LAPTOP.md" "$OUT_DIR/"
( cd "$OUT_DIR" && sha256sum auditree-bundle.tgz.gpg.part-* > SHA256SUMS )

echo
ls -lh "$OUT_DIR"
echo
echo "Done. Next: push it -- see 'Push' in $OUT_DIR/README.md"
