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

Kind: build
Plan: decisions/rm-path-wrapper.md#the-ruling (macos)
Plan: decisions/rm-path-wrapper.md#the-ruling (linux)
Home: bin/rm
