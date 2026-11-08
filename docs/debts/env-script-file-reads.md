# A script written in one call and run in a later call reads the env file

- **What.** The env-file guard judges a script file only when one command writes and runs it (`cat > dbg.py <<'PY' ... PY` then `python3 dbg.py`). A script written in one tool call and run in a later call reads the file, and no per-command guard sees the link between the two calls. A session debugging config is likely to write such a script (the retired interpreter-code debt said so).
- **Where.** `hooks/guard_env.py` (`_heredoc_code`), `hooks/guard_core.py` (`heredoc_code`, `code_paths`). The gap is in the run call, which names only the script file.
- **Decision.** `env-file-stays-unread` (a session never reads an environment file).
- **Retire.** A record of the script files a session wrote, read when a later call runs one with python or node, so the run is judged as code. A case in `hooks/test_guard.py` denies the run call. Fix: none — a per-command guard cannot see a file written in an earlier call. Until: 2026-11-21.
