# AGENTS.md

The agent guide for this repository lives in **[CLAUDE.md](CLAUDE.md)**.

Read it in full before making any change. It is tool-agnostic — Claude Code loads it
automatically, other assistants should read it explicitly.

Three things that will bite you immediately if you skip it:

1. **Never `git add -A`.** ~3,566 files show as modified from file-mode churn only
   (`100755 → 100644`). Stage explicit paths.
2. **Untracked ≠ gitignored.** `local-dev.conf` and `start-local.sh` sit untracked but
   uncovered by `.gitignore` and contain plaintext passwords.
3. **Write ASCII only.** Non-ASCII characters have been corrupted in this tree before,
   including in user-visible field labels.
