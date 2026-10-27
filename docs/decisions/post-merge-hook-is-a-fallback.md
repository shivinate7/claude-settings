# The post-merge hook exists only while symlinks fail

## The ruling

Owner, 2026-10-22: `install.ps1` writes its git post-merge hook only when it installs a copy, not a link. That means settings.json when the symlink or the replace fails, or an agent or skill that cannot be linked. The hook re-copies those files after each merge into the clone's main. When symlinks work, `install.ps1` deletes the hook if it carries the marker line `# claude-settings post-merge hook`, and logs `hook=removed`. A hook without the marker is not ours and stays untouched.

- Both link exits (the first run that makes the links, and a rerun over links already made) call one helper, so both remove it, or both keep it.
- One case keeps it: settings.json is linked but an agent or skill was copied. The hook still refreshes the copy, and the log says `hook=installed`.
- A delete that fails (a handle holds the hook) logs a line naming the hook and the error, writes `hook=delete failed`, and the run still writes its summary line.
- Copy mode still writes the hook and logs `hook=installed`.

Why: a hook written on 2026-10-15, when symlinks failed, stayed after symlinks worked, because `install.ps1` logged `hook=not needed` and left it. On 2026-10-21 it ran after the merges at 11:57 and 17:22. Each time it copied `bin/rm` into `~/.claude/bin`, a file that must not exist on Windows. Protected by the `hookgone1`, `hookgone1b`, `hookkeep1`, `hookkeep1b`, `hookkeepagents1`, `hookkeepagents1b`, `hookgonefail1` and `hookwrite1` cases in `install.test.ps1`.

## Limits

- A marked hook in a clone that `install.ps1` never runs against stays until a run there.

Kind: build
Plan: docs/decisions/post-merge-hook-is-a-fallback.md#the-ruling (windows)
Home: install.ps1
