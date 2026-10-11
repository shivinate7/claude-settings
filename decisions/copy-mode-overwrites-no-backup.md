# Copy mode overwrites and keeps no backup

## The finding, 2026-10-03

This Windows machine cannot make symlinks. Developer Mode is off by company policy. The
SessionStart hook runs `install.sh` through Git Bash, and Git Bash `ln -s` makes a copy,
not a link. The next run saw a real file, moved it to `.bak.<time>`, and copied again.
After two weeks, `~/.claude` held 3,090 `.bak` entries. The skill backups loaded as real
skills: 26 copies each of `ci-hygiene` and `fresh-prose`. The skills branch of
`install.ps1` and its post-merge hook have the same fault. The copies went to the
Recycle Bin on 2026-10-03.

## The ruling

Owner, 2026-10-03: in copy mode, an installer overwrites its own old copy. It keeps no
backup.

Owner, 2026-10-11, one exception: `settings.json`. When a repeat install finds a plain file
there and not the link, it moves the file to a new `settings.json.bak.<time>` first. Then
it removes each older `settings.json.bak.*`, so only the newest backup stays. The first
local install keeps the person's own file as `settings.json.orig`, which is never removed.
If a move fails, the install stops before it removes or links anything. This cap keeps
the 2026-10-03 pile-up from coming back. The reason: each merge now runs the install. A
tool that writes `settings.json` as a plain file would lose its edits at the next merge.

Known cost: a hand edit to any other installed copy under `~/.claude` is lost at the next
install.
