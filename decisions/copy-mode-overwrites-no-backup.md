# Copy mode overwrites and keeps no backup

## The finding, 2026-10-03

This Windows machine cannot make symlinks. Developer Mode is off by company policy. The
SessionStart hook runs `install.sh` through Git Bash, and Git Bash `ln -s` makes a copy,
not a link. The next run saw a real file, moved it to `.bak.<time>`, and copied again.
After two weeks, `~/.claude` held 3,090 `.bak` entries. The skill backups loaded as real
skills: 26 copies each of `ci-hygiene` and `fresh-prose`. The skills branch of
`install.ps1` and its post-merge hook have the same fault. The copies went to the
Recycle Bin on 2026-10-03.

## The ruling, 2026-10-03

The owner ruled: in copy mode, an installer overwrites its own old copy. It keeps no
backup.

Known cost: a hand edit to an installed copy under `~/.claude` is lost at the next
session start.

Status: not built. The fix touches `install.sh`, `install.ps1` and the post-merge hook
that `install.ps1` writes. It needs the owner's word to start.
