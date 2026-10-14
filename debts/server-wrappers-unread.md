# A server behind some wrappers is unchecked

- **What.** The `background-end` rule does not read some wrappers and forms, so a background server behind them is not refused without an `until:` note. Not read: `uv run`, `poetry run`, `cross-env`, `concurrently`, `Start-Process`, `cmd /d /c`, `exec`, `x=$(...)`, `yarn workspace <w> dev`, and python options with values before `-m` (`-X utf8`).
- **Where.** `hooks/guard_stream.py`, the `background-end` rule, `_tokens_hit` and `server_program`.
- **Decision.** `background-needs-end-note` (a background server or watcher needs an `until:` note at start).
- **Retire.** Read each form through to the command it runs. A test case per form, a server under `run_in_background` with no note, is red before the change and green after it.
