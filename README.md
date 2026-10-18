# Laptop migration bundle

Moves the Auditree dev environment to a new laptop as an encrypted bundle
(gpg AES-256, symmetric passphrase), split into 90 MB parts so GitHub accepts it.

## Old laptop -- pack (WSL terminal)

```bash
cd ~/Projects/Auditree
./start-local.sh stop                      # avoid files changing mid-tar
bash scripts/laptop-migration/pack.sh      # writes ~/auditree-migration/
```

Pick a long passphrase (16+ chars) and keep it OUT of git / chat / email.
It is the only thing protecting deploy/secrets/prod.env and your SSH keys.

## Push -- to an orphan branch, never to main

```bash
cd ~/Projects/Auditree
git worktree add --orphan -b laptop-migration /tmp/lm
cp ~/auditree-migration/* /tmp/lm/
cd /tmp/lm
git add auditree-bundle.tgz.gpg.part-* SHA256SUMS unpack.sh README.md
git commit -m "chore: encrypted laptop migration bundle"
git push origin laptop-migration
cd ~/Projects/Auditree && git worktree remove /tmp/lm
```

## New laptop -- restore (Ubuntu 24.04, WSL or native)

The SSH key is inside the bundle, so fetch the branch over HTTPS
(GitHub username + a personal access token when prompted):

```bash
git clone --single-branch -b laptop-migration \
    https://github.com/fowadhamza/auditree-odoo.git ~/auditree-migration
cd ~/auditree-migration && bash unpack.sh
```

`unpack.sh` installs apt packages, decrypts, restores the project to
`~/Projects/Auditree` (with .git, so all branches and uncommitted work come back),
SSH keys, the local database + filestore, re-clones Odoo core at the same commit,
builds a venv and points `start-local.sh` at it. Follow the checklist it prints.

## Clean up afterwards

```bash
git push origin --delete laptop-migration
rm -rf ~/auditree-migration
```

Deleting the branch does not guarantee GitHub purges the objects immediately,
so treat the bundle as "encrypted, but out there": if the passphrase was weak,
rotate prod.env secrets and SSH keys.
