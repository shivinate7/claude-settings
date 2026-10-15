# Data piped into python behind a wrapper is read as code

- **What.** Text piped into `head`, `tail` or `sort`, or into `VAR=x python`, `python3.12`, `py` or `verdict python`, is read as a python program, so a cap or frozen-path write named in that text denies. `_kind` sees only a bare `python` or `python3` command word. The text is data, so each deny is a false alarm. The same on main.
- **Where.** `_kind` and `_runs_a_file` in `hooks/guard_frozen.py`, read by `_shell_write_hit`.
- **Decision.** `subagent-model-cap`, the ruling for the cap ask on shell data. No entry names `_shell_write_hit` itself.
- **Retire.** A test shows that data piped into each wrapper allows, and that a program piped into `python -` still denies.
