#!/usr/bin/env bash
# Rebuild the Auditree dev environment on a new laptop from the encrypted bundle
# made by pack.sh. Target: Ubuntu 24.04 (WSL or native).
#
# Usage, from the folder holding the bundle parts + SHA256SUMS:
#   bash unpack.sh
# Env:
#   SKIP_APT=1   don't apt-install system packages
#   TARGET=...   where the project goes (default ~/Projects/Auditree)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="${TARGET:-$HOME/Projects/Auditree}"
[ -e "$TARGET" ] && { echo "$TARGET already exists -- refusing to overwrite"; exit 1; }

echo "== 1/8 system packages"
if [ "${SKIP_APT:-0}" != "1" ]; then
    sudo apt-get update
    sudo apt-get install -y git gnupg postgresql postgresql-client \
        python3 python3-venv python3-dev build-essential libpq-dev \
        libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libjpeg-dev \
        zlib1g-dev libffi-dev node-less wkhtmltopdf
fi

echo "== 2/8 verify + decrypt"
( cd "$HERE" && sha256sum -c SHA256SUMS )
read -r -s -p "Bundle passphrase: " PASS; echo
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cat "$HERE"/auditree-bundle.tgz.gpg.part-* \
  | gpg --batch --pinentry-mode loopback --passphrase-fd 3 -d 3<<<"$PASS" \
  | tar -xzf - -C "$STAGE"
META="$STAGE/migration-meta"
DB_NAME="$(cat "$META/db_name")"
OLD_HOME="$(cat "$META/old_home")"

echo "== 3/8 project -> $TARGET"
mkdir -p "$(dirname "$TARGET")"
mv "$STAGE/Auditree" "$TARGET"

echo "== 4/8 ssh keys + gitconfig"
if [ -d "$HOME/.ssh" ] && [ -n "$(ls -A "$HOME/.ssh")" ]; then
    mv "$STAGE/.ssh" "$HOME/.ssh.from-old-laptop"
    echo "   ~/.ssh already exists -- old keys left in ~/.ssh.from-old-laptop, merge by hand"
else
    rm -rf "$HOME/.ssh"; mv "$STAGE/.ssh" "$HOME/.ssh"
fi
chmod 700 "$HOME"/.ssh* ; find "$HOME"/.ssh* -type f ! -name '*.pub' -exec chmod 600 {} +
if [ -f "$STAGE/.gitconfig" ]; then
    [ -f "$HOME/.gitconfig" ] && cp "$STAGE/.gitconfig" "$HOME/.gitconfig.from-old-laptop" \
                              || cp "$STAGE/.gitconfig" "$HOME/.gitconfig"
fi

echo "== 5/8 path fix-ups ($OLD_HOME -> $HOME)"
if [ "$OLD_HOME" != "$HOME" ]; then
    for f in local-dev.conf odoo.conf auditreelive-server.conf start-local.sh .start17.sh; do
        if [ -f "$TARGET/$f" ]; then sed -i "s#$OLD_HOME#$HOME#g" "$TARGET/$f"; fi
    done
fi
DEFAULT_TARGET="$HOME/Projects/Auditree"
if [ "$TARGET" != "$DEFAULT_TARGET" ]; then
    for f in local-dev.conf start-local.sh; do
        sed -i "s#$DEFAULT_TARGET#$TARGET#g" "$TARGET/$f"
    done
fi
CONF="$TARGET/local-dev.conf"
DB_PASS="$(sed -n 's/^db_password *= *//p' "$CONF")"
sed -i "s/^db_user *=.*/db_user = $USER/" "$CONF"

echo "== 6/8 Odoo core (odoo/odoo 17.0 @ $(cat "$META/odoo-core.commit"))"
CORE="$TARGET/auditreelive-server"
git init -q -b 17.0 "$CORE"
git -C "$CORE" remote add origin https://github.com/odoo/odoo
git -C "$CORE" fetch --depth 1 origin "$(cat "$META/odoo-core.commit")"
git -C "$CORE" checkout -q FETCH_HEAD
git -C "$CORE" branch -q -f 17.0 FETCH_HEAD && git -C "$CORE" checkout -q 17.0
git -C "$CORE" branch -q --set-upstream-to=origin/17.0 17.0 2>/dev/null || true
if [ -s "$META/odoo-core.diff" ]; then
    git -C "$CORE" apply "$META/odoo-core.diff" && echo "   applied local core diff"
fi
if [ -f "$META/odoo-core-untracked.tgz" ]; then
    tar -C "$CORE" -xzf "$META/odoo-core-untracked.tgz" && echo "   restored untracked core files"
fi

echo "== 7/8 python venv"
python3 -m venv "$TARGET/venv"
VPIP="$TARGET/venv/bin/pip"
"$VPIP" install -q --upgrade pip wheel
"$VPIP" install -r "$CORE/requirements.txt"
# external_dependencies declared by the custom addons
EXTRA="$(python3 - "$TARGET/custom/addons" <<'PY'
import ast, pathlib, sys
pkgs = set()
for m in pathlib.Path(sys.argv[1]).glob('*/__manifest__.py'):
    try:
        d = ast.literal_eval(m.read_text(encoding='utf-8', errors='replace'))
        pkgs.update(d.get('external_dependencies', {}).get('python', []))
    except Exception:
        pass
print(' '.join(sorted(pkgs)))
PY
)"
if [ -n "$EXTRA" ]; then
    echo "   addon deps: $EXTRA"
    "$VPIP" install $EXTRA || echo "   WARNING: some addon deps failed"
fi
# start-local.sh used the system python3; point it at the venv instead
sed -i "s#python3 odoo-bin#$TARGET/venv/bin/python odoo-bin#g" "$TARGET/start-local.sh"

echo "== 8/8 PostgreSQL + database + filestore"
sudo service postgresql start || true
sudo -u postgres psql -qc "DO \$\$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='$USER') THEN CREATE ROLE \"$USER\" LOGIN SUPERUSER; END IF; END\$\$;"
sudo -u postgres psql -qc "ALTER ROLE \"$USER\" PASSWORD '$DB_PASS';"
createdb "$DB_NAME"
pg_restore --no-owner --role="$USER" -d "$DB_NAME" "$META/$DB_NAME.dump" || echo "   (pg_restore warnings above are usually harmless)"
if [ -d "$STAGE/filestore/$DB_NAME" ]; then
    mkdir -p "$HOME/.local/share/Odoo/filestore"
    mv "$STAGE/filestore/$DB_NAME" "$HOME/.local/share/Odoo/filestore/"
fi

if [ -d "$META/claude-memory" ]; then
    rm -rf "$HOME/claude-memory-from-old-laptop"
    mv "$META/claude-memory" "$HOME/claude-memory-from-old-laptop"
fi
mkdir -p "$TARGET/migration-meta" && cp "$META"/*.txt "$META"/odoo-core.* "$TARGET/migration-meta/" 2>/dev/null || true

cat <<EOF

Done. Remaining by hand:
  1. start-local.sh line 32 holds the OLD laptop's sudo password -- edit it.
  2. cd $TARGET && ./start-local.sh start   then open http://localhost:8069
  3. ssh -T git@github.com    (GitHub key test)   then: git status / git branch -a
  4. gcloud: install the CLI, then 'gcloud auth login' + 'gcloud config set project auditree-prod'
  5. Claude memory: copy ~/claude-memory-from-old-laptop/* into the new project's
     ~/.claude/projects/<project-key>/memory/ folder (open the project in Claude Code once first).
  6. Delete the bundle branch from GitHub once everything works (see README).
EOF
