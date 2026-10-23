# Laptop migration -- step-by-step checklist

Everything needed to move the Auditree dev environment and Claude Code sessions
from the old laptop to the new one, in order. Tick each box as you go.

Readable on GitHub without cloning: repo `fowadhamza/auditree-odoo` -> branch
`laptop-migration` -> `MIGRATION-STEPS.md`.

Details and troubleshooting: `NEW-LAPTOP.md` on the same branch.

---

## Part A -- Old laptop (IBM)

- [x] A1. Packed the dev environment: `bash scripts/laptop-migration/pack.sh`
      -> `~/auditree-migration/` (4 parts, 330 MB)
- [x] A2. Tested the passphrase decrypts the bundle
- [x] A3. Packed Claude Code data: `pack-claude.ps1`
      -> `C:\Users\FowadHamza\claude-migration\` (2 parts, 92 MB)
- [x] A4. Both committed to the `laptop-migration` branch
- [ ] A5. **Push the branch** -- WSL terminal:
      ```bash
      cd ~/Projects/Auditree
      git push origin laptop-migration
      ```
- [ ] A6. Confirm on GitHub that branch `laptop-migration` shows `claude/`,
      `auditree-bundle.tgz.gpg.part-000..003`, `unpack.sh`, `NEW-LAPTOP.md`
- [ ] A7. Confirm the repo is **Private** (GitHub -> Settings -> General)

Keep the old laptop untouched until Part C is finished.

---

## Part B -- New laptop

### Before you start

- [ ] B0. Have these ready:
  - the bundle passphrase
  - a GitHub personal access token -- github.com -> Settings -> Developer
    settings -> Personal access tokens (classic) -> scope `repo`
  - your Windows admin rights (for installing WSL)

### Ubuntu + dev environment

- [ ] B1. Install Ubuntu -- PowerShell **as Administrator**:
      ```powershell
      wsl --install -d Ubuntu-24.04
      ```
      Reboot if asked. Open "Ubuntu 24.04" from the Start menu and create the
      Linux user **`fowadhamza`** (same name keeps paths and Claude sessions working).

- [ ] B2. Download the bundle -- Ubuntu terminal:
      ```bash
      sudo apt-get update && sudo apt-get install -y git
      git clone --single-branch -b laptop-migration \
          https://github.com/fowadhamza/auditree-odoo.git ~/auditree-migration
      ```
      Username `fowadhamza`, password = the access token.

- [ ] B3. Restore everything:
      ```bash
      cd ~/auditree-migration
      bash unpack.sh
      ```
      Asks for your sudo password, then the bundle passphrase. Takes 20-40 min.
      Ends with "Done. Remaining by hand".

- [ ] B4. Replace the old sudo password on line 32 of `start-local.sh`:
      ```bash
      cd ~/Projects/Auditree
      nano start-local.sh
      ```

- [ ] B5. Start Odoo:
      ```bash
      ./start-local.sh start
      ```
      Open http://localhost:8069 and log in. If it doesn't load, use the WSL IP
      from `hostname -I` instead of localhost.

- [ ] B6. Check GitHub over SSH:
      ```bash
      ssh -T git@github.com     # "Hi fowadhamza! ..."
      git branch -a             # main, feature/it-helpdesk, ...
      ```
      Thousands of mode-only changes in `git status` are normal (CLAUDE.md 3.1).
      Never `git add -A`.

- [ ] B7. Google Cloud access (only if you deploy to prod from this laptop):
      install the gcloud CLI (https://cloud.google.com/sdk/docs/install#deb), then
      ```bash
      gcloud auth login
      gcloud config set project auditree-prod
      ```

### Claude Code sessions

- [ ] B8. Install on Windows: **Git for Windows**, **VS Code**, the **Claude Code**
      extension. Sign in to Claude Code once, then **close VS Code**.

- [ ] B9. Copy the Claude data to Windows -- Ubuntu terminal
      (replace `<WinUser>` with your Windows user folder name):
      ```bash
      cp -r ~/auditree-migration/claude /mnt/c/Users/<WinUser>/claude-migration
      ```

- [ ] B10. Restore it -- normal PowerShell:
      ```powershell
      cd $env:USERPROFILE\claude-migration
      powershell -ExecutionPolicy Bypass -File .\restore-claude.ps1
      ```
      Enter the passphrase used for `pack-claude.ps1`.

- [ ] B11. Open the project in VS Code:
      `\\wsl.localhost\Ubuntu-24.04\home\fowadhamza\Projects\Auditree`
      Old sessions appear in Claude Code's session history.
      (If you chose a different Linux username, see NEW-LAPTOP.md section 4e.)

- [ ] B12. If the new laptop is **not** IBM-managed: delete the memory
      `no-wsl-execution-on-managed-laptop.md` and its line in `MEMORY.md` --
      that restriction was about the old device.

---

## Part C -- Clean up (only after Part B works)

- [ ] C1. New laptop -- delete the bundle from GitHub and disk:
      ```bash
      git -C ~/Projects/Auditree push origin --delete laptop-migration
      rm -rf ~/auditree-migration ~/claude-memory-from-old-laptop
      ```
      ```powershell
      Remove-Item -Recurse -Force $env:USERPROFILE\claude-migration
      ```
- [ ] C2. Revoke the GitHub access token if it was only for this.
- [ ] C3. Old laptop -- remove local copies:
      ```bash
      cd ~/Projects/Auditree && git branch -D laptop-migration
      rm -rf ~/auditree-migration
      ```
      ```powershell
      Remove-Item -Recurse -Force $env:USERPROFILE\claude-migration
      ```
- [ ] C4. If the passphrase was ever written somewhere insecure: rotate the
      secrets in `deploy/secrets/prod.env` and generate new SSH keys.

---

## If something fails

| Problem | Fix |
|---|---|
| `decryption failed` / `Bad session key` | Wrong passphrase -- run the script again |
| `checksum mismatch` / `did NOT match` | Corrupt download -- delete the folder and clone again |
| `~/Projects/Auditree already exists` | Earlier run stopped partway: `rm -rf ~/Projects/Auditree` (and `dropdb AUDITREE_LIVE_NEW` if the DB was created), re-run |
| Odoo: `No module named 'x'` | `~/Projects/Auditree/venv/bin/pip install x`, then `./start-local.sh restart` |
| Old Claude sessions not listed | Project opened from a different path -- see NEW-LAPTOP.md 4e |

More in `NEW-LAPTOP.md` -> Troubleshooting.
