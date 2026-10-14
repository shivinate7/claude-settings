# A background node file server is unchecked

- **What.** `node <file>` under `run_in_background` is not refused without an `until:` note. The roster cannot tell a server script from a one-off script.
- **Where.** `hooks/guard_stream.py`, the `background-end` rule, `server_program`.
- **Decision.** `background-needs-end-note` (a background server or watcher needs an `until:` note at start).
- **Retire.** Name a rule for `node <file>`, such as a name list or a flag. A test case for `node server.js` under `run_in_background` with no note is red before the change and green after it.
