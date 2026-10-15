# Text piped into an interpreter denies, as on main

- **What.** A quoted cap key or frozen path piped into an interpreter denies: `python hooks/guard.py`, `python run.py`, `python -`, and wrappers such as `head`, `tail`, `sort`, `VAR=x python`, `python3.12`, `py` or `verdict python`. The text is often data, so such a deny can be a false alarm. This is the same as on main. The guard cannot tell a program that reads its stdin as data from one that runs it, so it fails closed. Only a pipe into a pure printer (`echo`, `printf`, `cat`, `grep`, `wc`, `jq`) makes the text data.
- **Where.** `runs_nowhere` in `_shell_write_hit`, `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader. It does not name this friction.
- **Retire.** The reader knows which interpreters read stdin as data, or the owner rules that the friction stays. A test shows the chosen answer.
