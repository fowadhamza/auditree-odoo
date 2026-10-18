# New laptop setup -- Auditree dev environment

Step-by-step for rebuilding the Auditree Odoo dev environment from the encrypted
bundle on the `laptop-migration` branch. Takes roughly 30-45 minutes, most of it
apt and pip downloads.

You need:
- the bundle passphrase (chosen when pack.sh ran -- not stored anywhere else)
- a GitHub personal access token (github.com -> Settings -> Developer settings ->
  Personal access tokens -> classic, scope `repo`). Needed once, because your SSH
  key is inside the bundle and can't be used to download it.

---

## 1. Ubuntu 24.04

**Windows laptop** -- PowerShell as Administrator:

```powershell
wsl --install -d Ubuntu-24.04
```

Reboot if asked, open "Ubuntu 24.04" from the Start menu, and create your Linux
user. Using `fowadhamza` again avoids path rewrites, but any name works --
unpack.sh rewrites paths in the configs.

**Linux laptop** -- nothing to do if it already runs Ubuntu 24.04.

## 2. Download the bundle

In the Ubuntu terminal:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone --single-branch -b laptop-migration \
    https://github.com/fowadhamza/auditree-odoo.git ~/auditree-migration
```

Username: `fowadhamza`. Password: paste the access token (not your GitHub password).

## 3. Run the restore

```bash
cd ~/auditree-migration
bash unpack.sh
```

It asks for your sudo password (apt, PostgreSQL) and then the bundle passphrase.
What it does, in order:

| Step | Result |
|---|---|
| 1/8 | apt installs PostgreSQL, Python build deps, wkhtmltopdf, etc. |
| 2/8 | checks SHA256SUMS, decrypts and extracts |
| 3/8 | project -> `~/Projects/Auditree` (with `.git`: every branch, uncommitted work, untracked files) |
| 4/8 | `~/.ssh` (GitHub, DigitalOcean, GCP keys) + `~/.gitconfig` |
| 5/8 | rewrites old paths in `local-dev.conf` / `start-local.sh` if your home dir changed |
| 6/8 | clones odoo/odoo 17.0 at the old commit, applies the local core diff + untracked core files |
| 7/8 | builds `~/Projects/Auditree/venv` with Odoo + addon Python deps; points `start-local.sh` at it |
| 8/8 | PostgreSQL role + `AUDITREE_LIVE_NEW` database restore + filestore |

## 4. Finish by hand

**a. Fix the sudo password in start-local.sh** (line 32 still has the old laptop's):

```bash
cd ~/Projects/Auditree
nano start-local.sh        # line 32: echo '<new sudo password>' | sudo -S service postgresql start
```

**b. Start Odoo and log in:**

```bash
./start-local.sh start
./start-local.sh status
```

Open http://localhost:8069. On WSL, if localhost does not answer, use the WSL IP
instead: `hostname -I` -> http://<that IP>:8069 (it changes on every WSL restart).

**c. Check git and GitHub:**

```bash
ssh -T git@github.com          # "Hi fowadhamza! You've successfully authenticated"
git status | head
git branch -a                  # feature/it-helpdesk, main, the feature branches
```

`git status` may show thousands of mode-only changes (100755 -> 100644). That is
the known churn described in CLAUDE.md section 3.1 -- not something the move broke.
Never `git add -A`.

**d. Google Cloud (prod access):**

```bash
# install: https://cloud.google.com/sdk/docs/install#deb
gcloud auth login
gcloud config set project auditree-prod
gcloud compute ssh auditreelive-prod-mum --zone=asia-south1-a --tunnel-through-iap
```

The SSH firewall rule only allowlists specific IPs; `--tunnel-through-iap` works
from any network.

**e. Claude Code sessions, memory and settings.** The `claude/` folder of the
branch holds a separately encrypted copy of `%USERPROFILE%\.claude` from the old
laptop: all session transcripts (Auditree + AmityOdoo), memory, settings, skills,
plugins, plans. Restore it on the Windows side:

1. Install Git for Windows (provides gpg), VS Code and the Claude Code extension;
   log in to Claude Code once, then close VS Code.
2. Copy the folder to Windows -- in the Ubuntu terminal:
   `cp -r ~/auditree-migration/claude /mnt/c/Users/<WinUser>/claude-migration`
3. In PowerShell:
   ```powershell
   cd $env:USERPROFILE\claude-migration
   powershell -ExecutionPolicy Bypass -File .\restore-claude.ps1
   ```
4. Open `\\wsl.localhost\Ubuntu-24.04\home\fowadhamza\Projects\Auditree` in VS Code;
   the old sessions appear in Claude Code's session history (or `claude --resume`).

Sessions are keyed by the project path. If your distro or Linux username differs
from `Ubuntu-24.04` / `fowadhamza`, rename the folder under
`%USERPROFILE%\.claude\projects\` to match -- e.g. user `fowad` would need
`--wsl-localhost-Ubuntu-24-04-home-fowad-Projects-Auditree`. Simplest is to open
the project once, see which folder Claude Code creates, and move the old files
into it.

`~/.claude.json` is not swapped in automatically (it would clobber the new login);
the old one is saved as `.claude.json.from-old-laptop` if you need MCP server or
other settings from it.

If the new laptop is not IBM-managed, delete `no-wsl-execution-on-managed-laptop.md`
and its line in `MEMORY.md` -- that restriction was about the old device.

## 5. Clean up

Once Odoo runs and you can push from the new laptop:

```bash
git -C ~/Projects/Auditree push origin --delete laptop-migration
rm -rf ~/auditree-migration ~/claude-memory-from-old-laptop
```

Revoke the GitHub access token if you made it only for this. On the old laptop:
`git branch -D laptop-migration` and `rm -rf ~/auditree-migration`.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `sha256sum: WARNING ... did NOT match` | Download was corrupted. `rm -rf ~/auditree-migration` and clone again. |
| `decryption failed: Bad session key` | Wrong passphrase. Re-run `bash unpack.sh`. |
| `~/Projects/Auditree already exists -- refusing` | A previous run got partway. `rm -rf ~/Projects/Auditree`, then re-run. If it got past step 8, also `dropdb AUDITREE_LIVE_NEW`. |
| `git apply` fails in step 6/8 | Core diff did not match the fetched commit. Copy `auditreelive-server/` from the old laptop instead (or its `auditreelive-server.tar.gz`), then re-run the rest by hand. |
| `pg_restore` warnings about owners/extensions | Usually harmless -- the script continues. Check Odoo starts. |
| Odoo log: `ModuleNotFoundError: No module named 'x'` | `~/Projects/Auditree/venv/bin/pip install x`, then `./start-local.sh restart`. |
| PDF reports blank or broken | Ubuntu's wkhtmltopdf is the unpatched build. Install 0.12.6.1 "with patched qt" from github.com/wkhtmltopdf/packaging/releases. |
| Different behaviour from prod | Local now runs Python 3.12 (Ubuntu 24.04), prod runs 3.10. Usually fine for Odoo 17; suspect it if a bug only reproduces in one place. |

## What is NOT in the bundle

Still on the old laptop only -- copy over manually if you want them:

- `auditreelive-server.tar.gz`, `AUDITREE_ADDONS.tar.gz`, `AUDITREE_FILESTORE.tar.gz`,
  `AUDITREE_LIVE_NEW.dump` (old backups; the bundle has a fresh DB dump instead)
- dated prod-data copies under `deploy/migration-work`, `deploy/do-sync`,
  `deploy/gcp-backup` (copies also live in `gs://auditree-prod-backups/`)
- `auditreelive-server/OLD-addons/` (stale backup copy, never loaded)
- anything outside `~/Projects/Auditree`, `~/.ssh`, `~/.gitconfig` and the Odoo
  filestore -- e.g. gcloud credentials, shell history, VS Code settings
