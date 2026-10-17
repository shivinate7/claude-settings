# An rm shim on PATH, active only in Claude sessions

## The question

What stops a recursive delete of `/`, the home folder, the working folder or a parent of it, after
the `rm-var` guard rule and the prompt-answer hook (decision rm-on-a-variable-needs-a-guard, rm on a
variable needs a `:?` guard)? Those two read the command text. A shim reads the path at run time.

## The ruling

Owner, 2026-10-11 ("Yes, only for Claude sessions"): `bin/rm` sits ahead of the real `rm` on PATH.

- `bin/rm` is a POSIX `sh` front. `CLAUDECODE` unset: it execs the real `rm` at once, with no Python.
  MEASURED 2026-10-12: a Claude Code session sets `CLAUDECODE=1` in every Bash tool process.
- `CLAUDECODE` set and no argument is a flag that holds `r` or `R`: it execs the real `rm` at once.
  Only a possible recursive call runs the Python check.
- `CLAUDECODE` set and the call is recursive (`-r`, `-R`, `--recursive`, or a short-flag group that holds
  `r` or `R`): if any operand is `/`, home, the cwd or a parent of the cwd, symlinks resolved, the whole
  call is refused. Nothing runs. Exit 1, one line on stderr. The line names no delete command.
- Any other call runs the real `rm`: the first `rm` on PATH whose line 2 is not the shim marker
  (`# claude-settings-rm-shim`), else `/bin/rm`. Any copy of the shim is skipped, so two copies on PATH
  never call each other.
- A removed cwd does not stop the check. The shim then judges absolute operands against `/` and home,
  and skips relative ones, which the real `rm` cannot resolve either.
- The reading is `_rm_target_bad` in `hooks/guard_rm_var.py`, the one home. The shim finds `hooks/`
  from its own real path, so a symlinked install and a copied install both work.
- `install.sh` needs no new step. `land_dir bin` links `bin/rm` into `~/.claude/bin`, and the existing
  rc line puts `~/.claude/bin` first on PATH, so it wins over `/bin/rm`.

CI: `lint/test_rm_shim.py` runs in `gates` and `gates-macos`. `harness-scope.sh` maps `bin/rm` and the test.

## Why fail-open

If `python3` is missing, or `guard_rm_var` cannot load, or the judgment raises, the shim prints one
warning line and runs the real `rm`. The shim sits in front of every `rm` a Claude session runs, so a broken helper that refused
would stop all deletes, including safe ones. The rule and the hook are the first stops. The shim is the
last stop, and a missing last stop is a smaller harm than a session that cannot delete a file.
MEASURED 2026-10-17: a copy of the shim with no `hooks/` beside it printed the warning and deleted.

## Holes, named

- The call must reach the shim. `/bin/rm`, `command rm`, `env -i rm`, a shell with no rc PATH line, and
  `find -delete` skip it. Debt `rm-shim-bypass-forms` (a full-path rm skips the shim).
- Windows has no shim. `bin/rm` is posix only, and `install.ps1` skips it in both its landing loop and
  the post-merge hook it writes. Debt `rm-shim-windows` (the install.ps1 half).
- A cloud install adds no PATH line, so the shim is off there. Debt `rm-shim-cloud-path` (cloud
  sessions do not get the shim).
- The shell expands globs first. `rm -rf *` in the cwd arrives as a list of children, so it passes.
  The cwd itself is not an operand. Debt `rm-shim-glob-passes` (an expanded glob passes).
- Flags are read anywhere before `--`. On macOS `rm dir -rf` treats `-rf` as a file name, so the shim
  refuses a call that BSD `rm` would not have run as recursive. A false alarm that costs one retry.
  Debt `rm-shim-flag-order` (a flag after an operand is read as a flag).
- GNU abbreviations such as `--rec` and `--recur` are not read as recursive, so such a call passes
  unjudged. Debt `rm-shim-flag-order`.
- Cost per call, MEASURED 2026-10-17: real `rm` 1.9 ms. The shim with `CLAUDECODE` unset, or set and not
  recursive: 4.4 ms. Set and recursive: 40 ms, one Python start. Debt `rm-shim-call-cost` (a recursive
  call pays one Python start).
- The marker search reads the real `rm`'s first line byte by byte. MEASURED 2026-10-17: 4.4 ms under
  `sh`, 7.0 ms under `dash`. A 20 MB `rm` on PATH with no newline costs 1.6 s under `sh` and 5.7 s under
  `dash`. Debt `rm-shim-call-cost`.
- `rm -r link` is refused when `link` is a symlink to home, the cwd or a parent of the cwd. The real
  `rm` removes only the link. A false alarm that costs one retry. Debt `rm-shim-link-refused` (a
  recursive rm of a symlink is judged by its target).

Kind: build
Plan: decisions/rm-path-wrapper.md#the-ruling (macos)
Plan: decisions/rm-path-wrapper.md#the-ruling (linux)
Home: bin/rm
