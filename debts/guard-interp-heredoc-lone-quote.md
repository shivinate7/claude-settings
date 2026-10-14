# A lone quote in an interpreter heredoc hides a later command

- **What.** If an interpreter heredoc body such as `python3 - <<'PY'` holds a lone `'`, the guard reads the rest of the command as quoted. A later cited commit then runs unjudged. Bash runs it.
- **Example.** Two `python3 - <<'E'` heredocs, each body `x = it's`, then a commit with `-F - <<'B'` whose body names a record. Bash runs the commit, and the guard allows it.
- **Where.** `hooks/guard.py` (heredoc body reading) and `split_segments` in `hooks/guard_core.py`.
- **Decision.** `guard-command-position` (the guard reads each command where bash runs it).
- **Retire.** A quoted heredoc body is skipped as plain text in both readings. A case with a lone quote in a `<<'PY'` body before a cited commit denies.
