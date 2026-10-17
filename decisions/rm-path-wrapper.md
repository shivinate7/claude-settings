# An rm shim on PATH, active only in Claude sessions

## The ruling

`bin/rm` sits ahead of the real `rm` on PATH, for Claude sessions only. It stops a recursive delete of
`/`, the home folder, the working folder or a parent of it. The `rm-var` guard rule and the prompt-answer
hook (rm-on-a-variable-needs-a-guard) read the command text. The shim reads the path at run time.

- `bin/rm` is a POSIX `sh` front. `CLAUDECODE` unset: it execs the real `rm` at once, with no Python. A
  Claude Code session sets `CLAUDECODE=1` in every Bash tool process.
- `CLAUDECODE` set and no argument is a flag that holds `r` or `R`: it execs the real `rm` at once. Only
  a possible recursive call runs the Python check.
- `CLAUDECODE` set and the call is recursive (`-r`, `-R`, `--recursive`, or a short-flag group that holds
  `r` or `R`): if any operand is `/`, home, the cwd or a parent of the cwd, symlinks resolved, the whole
  call is refused. Nothing runs. Exit 1, one line on stderr. The line names no delete command.
- Any other call runs the real `rm`: the first `rm` on PATH whose line 2 is not the shim marker
  (`# claude-settings-rm-shim`), else `/bin/rm`. Any copy of the shim is skipped, so two copies on PATH
  never call each other.
- A removed cwd does not stop the check. The shim then judges absolute operands against `/` and home,
  and skips relative ones, which the real `rm` cannot resolve either.
- The reading is `_rm_target_bad` in `hooks/guard_rm_var.py`, the one home. The shim finds `hooks/` from
  its own real path, so a symlinked install and a copied install both work.
- `install.sh` needs no new step. `land_dir bin` links `bin/rm` into `~/.claude/bin`, and the existing rc
  line puts `~/.claude/bin` first on PATH, so it wins over `/bin/rm`.
- **Fail-open.** If `python3` is missing, or `guard_rm_var` cannot load, or the judgment raises, the shim
  prints one warning line and runs the real `rm`. The shim sits in front of every `rm` a Claude session
  runs, so a broken helper that refused would stop all deletes. The rule and the hook are the first
  stops. A missing last stop is a smaller harm than a session that cannot delete a file.

CI: `lint/test_rm_shim.py` runs in `gates` and `gates-macos`. `harness-scope.sh` maps `bin/rm` and the test.

Kind: build
Plan: decisions/rm-path-wrapper.md#the-ruling (macos)
Plan: decisions/rm-path-wrapper.md#the-ruling (linux)
Home: bin/rm

## Holes, named

- The call must reach the shim. `/bin/rm`, `command rm`, `env -i rm`, a shell with no rc PATH line, and `find -delete` skip it. Debt `rm-shim-bypass-forms`.
- Windows has no shim. `bin/rm` is posix only, and `install.ps1` skips it in its landing loop and in the post-merge hook it writes. Debt `rm-shim-windows`.
- A cloud install adds no PATH line, so the shim is off there. Debt `rm-shim-cloud-path`.
- The shell expands globs first. `rm -rf *` in the cwd arrives as a list of children, so it passes. Debt `rm-shim-glob-passes`.
- Flags are read anywhere before `--`. On macOS `rm dir -rf` treats `-rf` as a file name, so the shim refuses a call that BSD `rm` would not run as recursive. GNU abbreviations such as `--rec` are not read as recursive, so such a call passes unjudged. Debt `rm-shim-flag-order`.
- A recursive call pays one Python start (about 40 ms). The marker search reads the real `rm`'s first line byte by byte. Debt `rm-shim-call-cost`.
- `rm -r link` is refused when `link` is a symlink to home, the cwd or a parent of the cwd. The real `rm` removes only the link. Debt `rm-shim-link-refused`.
