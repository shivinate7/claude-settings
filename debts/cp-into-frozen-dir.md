# A copy into a frozen directory is allowed

- **What.** Measured on main: `cp /tmp/x <config>/hooks/`, `cp -t <config>/hooks /tmp/x`, `cp -t<config>/hooks /tmp/x` and `cp --target-directory=<config>/hooks /tmp/x` are allowed. The frozen test judges the named path, and a directory named alone (`hooks`, `lint`, `agents`) is outside the frozen set, so the copy lands a new file there. Measured on this branch: `link <frozen file> /tmp/x` is allowed, because `link` is not in `MUTATING_COMMAND`, and a later write to `/tmp/x` writes the frozen file.
- **Where.** `is_frozen`, `_shell_write_hit` and `MUTATING_COMMAND` in `hooks/guard_frozen.py`.
- **Decision.** `recovery-must-not-gate-on-its-own-state` (it lists the frozen paths).
- **Retire.** A destination that names a frozen directory counts as frozen, `link` joins `MUTATING_COMMAND`, and a new test denies each shape above. No test pins these shapes now. `_copy_reads` already tests `DEST/_` for the copy-out rule; the same test on every write target closes it.
