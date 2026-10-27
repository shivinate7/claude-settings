# Brief: c123, a cloud reinstall stops filling the skill list with backup copies

Repo: shivinate7/claude-settings, from main d4e1b86. One lane: builder (sonnet), then reviewer (sonnet).

## Task
`install.sh` moves an existing installed folder to `<dest>.bak.<time>` before it copies the fresh one. In a cloud session the install runs at every resume and after every merge, so `~/.claude/skills/` collects `<skill>.bak.<time>` folders, and each one lists as a skill (44 in one session on Oct 27).
- When the existing folder is the repo's own earlier install (identical source, or carrying the install's own marker), replace it with no backup.
- When a backup is still needed (a folder the user changed by hand), write it outside `skills/` (and outside every other folder Claude Code scans), so it never lists as a skill.
- Keep the backup for a user's own edits; never delete their work.

## Rulings
- verification-recovery-not-gated-on-own-state: the backup of a hand edit must still happen.

## Failure classes
- A hand-edited skill that gets overwritten with no copy.
- The same fix missing on Windows (install.ps1 or its equivalent, if it backs up the same way).

## Check that proves it done
A test that runs the installer twice into a temp home: red on main (a `.bak.*` folder in skills/), green on the branch (none), plus a case where a hand edit is kept outside skills/. Existing installer tests pass (hooks/test_install_src.sh, hooks/test_install_windows.sh where it can run). bin/ste-changed origin/main.

## Report
At most 12 lines: PR, head, red run, green run, review verdict. Send the green, reviewed head to the build advisor. Do not rebase onto main and do not merge.
