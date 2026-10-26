# An rm shim on PATH, active only in Claude sessions

## The ruling

`bin/rm` sits ahead of the real `rm` on PATH, for Claude sessions only. It stops a recursive delete of `/`, the home folder, the working
folder or a parent of it. The `rm-var` guard rule and the prompt-answer hook (rm-on-a-variable-needs-a-guard) read the command text. The
shim reads the path at run time.

- `bin/rm` is a POSIX `sh` front (posix only). `CLAUDECODE` unset: it execs the real `rm` at once, with no Python. A Claude Code session
  sets `CLAUDECODE=1` in every Bash tool process.
- `CLAUDECODE` set and no argument is a flag that holds `r` or `R`: it execs the real `rm` at once. Only a possible recursive call runs
  the Python check.
- `CLAUDECODE` set and the call is recursive (`-r`, `-R`, `--recursive`, or a short-flag group that holds `r` or `R`): if any operand is
  `/`, home, the cwd or a parent of the cwd, symlinks resolved, the whole call is refused. Nothing runs. Exit 1, one line on stderr. The
  line names no delete command.
- Any other call runs the real `rm`: the first `rm` on PATH whose line 2 is not the shim marker (`# claude-settings-rm-shim`), else
  `/bin/rm`. Any copy of the shim is skipped, so two copies on PATH never call each other.
- A removed cwd does not stop the check. The shim then judges absolute operands against `/` and home, and skips relative ones.
- The reading is `_rm_target_bad` in `hooks/guard_rm_var.py`, the one home. The shim finds `hooks/` from its own real path, so a symlinked
  install and a copied install both work.
- `land_dir bin` links `bin/rm` into `~/.claude/bin`, which the existing rc line puts first on PATH. `install.ps1` skips it.
- **Fail-open.** If `python3` is missing, or `guard_rm_var` cannot load, or the judgment raises, the shim prints one warning line and runs
  the real `rm`. The shim sits in front of every `rm` a Claude session runs, so a broken helper that refused would stop all deletes. The
  rule and the hook are the first stops. A missing last stop is a smaller harm than a session that cannot delete a file.
- **Line endings.** See decision shell-scripts-check-out-lf (shell scripts check out with LF).

## The guard holds the line on every platform

Owner ruling 2026-10-21: on Windows the shim does not judge. Its refusals sit in the guard's `destructive-delete` rule
(`hooks/guard.py`, `hooks/guard_push_delete.py`). The rule applies on every platform, in Bash and in PowerShell, and through the cmd verbs
`rd`, `rmdir`, `del` and `erase` with `/s`.

- Refused, with force or without: a recursive delete of `.`, `..` or a relative parent, quoted or not. The forms are `./`, `../`, `.\`
  and `..\`.
- Refused too: the absolute working folder or any folder above it (`/c/...`, `C:\...` and plain forms). Also a root, a home, or a glob of
  one (`rm -r /`, `rm -r ~/*`, `rm -r ../*`).
- PowerShell: `Remove-Item -Recurse`, its abbreviations and aliases, with `-Path`, `-LiteralPath` or a positional target.
- A folder change (`cd`, `pushd`, `Set-Location`, `sl`, `chdir`) earlier in the same command is not tracked. `.` and a relative parent stay
  refused after it. The reason then names the fix: `rm -rf ./build/*` empties a folder, and `rm -rf build` deletes it by name. In
  PowerShell the fix is `Remove-Item -Recurse build`.
- Allowed: `rm -rf ./build`, a sibling that is not a parent, and a call that is not recursive.

Accepted risk (owner, 2026-10-21): on Windows the guard reads the command text. It resolves a named folder through links already on disk.
It misses a link made earlier in the same command. It also misses a delete inside a script, a Makefile or an npm script, and a variable that
expands at run time to a parent. On Mac and Linux the shim still catches those. How often Claude writes such a delete is unmeasured.

Kind: build
Plan: docs/decisions/rm-path-wrapper.md#the-ruling (macos)
Plan: docs/decisions/rm-path-wrapper.md#the-ruling (linux)
Plan: docs/decisions/rm-path-wrapper.md#the-guard-holds-the-line-on-every-platform (windows)
Home: bin/rm
