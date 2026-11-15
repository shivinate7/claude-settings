# Copy mode overwrites and keeps no backup

## The ruling

Owner: in copy mode, an installer overwrites its own old copy and keeps no backup. Exception, `settings.json`: a repeat install that finds a plain file there, not the link, backs it up to a new `settings.json.bak.<time>.<pid>` and removes each older backup of that form. Only the newest stays.

- The first local install keeps the person's own file as `settings.json.orig`. It is never removed.
- A backup from an older installer, named `settings.json.bak.<time>` with no pid, stays.
- If the backup fails, the install stops before it replaces settings.json or removes an older backup.

Skill backups: a skill backup never lands in `skills/` or any folder Claude Code scans. It goes to `backups/skills/<name>.<time>` under the config dir. Older `skills/<name>.bak.*` folders are moved there, never deleted. A cloud run links each skill through its generation (`install-hooks-whole`). An older cloud run left a skill as a real copy. The link replaces it once. A copy that matches the tree hash recorded in `backups/skill-copies/`, or the source, goes with no backup. Any other copy is backed up. The hash covers file names and contents only, and leaves out `__pycache__` folders and `*.pyc` files (`install-hooks-whole`), so a mode, empty-folder, symlink-only or runtime-file change is replaced with no backup. The move takes only folders named `<name>.bak.<14 digits>`.

Why no backup: Git Bash `ln -s` makes a copy, so each install backed up the last copy. The `.bak` entries piled up and loaded as duplicate skills.

Why the exception: each merge runs the install. A tool that writes `settings.json` as a plain file would lose its edits at the next merge.

Known cost: a hand edit to any other installed copy under `~/.claude` is lost at the next install.

Kind: process
Home: install.sh
Home: install.ps1
