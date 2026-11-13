# Heredoc body kept in view when its written file runs

- **What.** The guard keeps a heredoc body in view when the file the body writes shares a pipeline with any runner word, even as a plain argument. So a body that names an env file (`.env`) refuses with `env-file` for `python3 check.py brief.md`, `python3 -m json.tool cfg.json`, `sudo cat f`, `timeout 5 wc f` and `ls f | xargs wc`. Main refuses these; a body with no env word passes. Write-then-validate in one call is normal work. Workaround: split it into two calls. Found by review, Nov 2 2026.
- **Where.** `hooks/guard_core.py`, `_runs_written_file` (lines 1009-1024), called from `strip_heredoc_bodies` (defined at line 1049).
- **Decision.** `env-file-stays-unread` (no session reads or writes an env file's contents; a quoted heredoc body is text).
- **Retire.** Each form in What, run as one call with the heredoc write and its run, passes the guard with no refusal. Until then the two-call workaround stands.
