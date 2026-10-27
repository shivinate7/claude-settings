# Copy mode overwrites and keeps no backup

## The ruling

Owner: in copy mode, an installer overwrites its own old copy and keeps no backup. Exception, `settings.json`: a repeat install that finds a plain file there, not the link, moves it to a new `settings.json.bak.<time>` and removes each older `settings.json.bak.*`. Only the newest backup stays.

- The first local install keeps the person's own file as `settings.json.orig`. It is never removed.
- A backup from an older installer, named `settings.json.bak.<time>` with no pid, stays.
- If a move fails, the install stops before it removes or links anything.

Skill backups: a skill backup never lands in `skills/` or any folder Claude Code scans. It goes to `backups/skills/<name>.<time>` under the config dir. Older `skills/<name>.bak.*` folders are moved there, never deleted. A cloud run records a tree hash of each skill it copies, in `backups/skill-copies/`. It replaces a copy with no backup when the copy matches that record or the source. Any other copy is backed up. The hash covers file names and contents only, so a mode, empty-folder or symlink-only change is replaced with no backup. The move takes only folders named `<name>.bak.<14 digits>`.

Why no backup: Git Bash `ln -s` makes a copy, so each install backed up the last copy. The `.bak` entries piled up and loaded as duplicate skills.

Why the exception: each merge runs the install. A tool that writes `settings.json` as a plain file would lose its edits at the next merge.

Known cost: a hand edit to any other installed copy under `~/.claude` is lost at the next install.

Kind: process
Home: install.sh
