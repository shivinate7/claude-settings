# A copy into a frozen directory is allowed

- **What.** Measured on main: `cp /tmp/x <config>/hooks/` and `cp -t <config>/hooks /tmp/x` are allowed. The frozen test judges the named path, and a directory named alone (`hooks`, `lint`, `agents`) is not under the frozen set, so the copy lands a new file there.
- **Where.** `is_frozen` and `_shell_write_hit` in `hooks/guard_frozen.py`.
- **Decision.** `recovery-must-not-gate-on-its-own-state` (it lists the frozen paths).
- **Retire.** A destination that names a frozen directory counts as frozen, and a test pins both shapes as deny. `_copy_reads` already tests `DEST/_` for the copy-out rule; the same test on every write target closes it.
