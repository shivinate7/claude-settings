# Guard rules from the 2026-10-13 audit

## The ruling

Owner, 2026-10-13 14:40, on an audit by the oversight session:

1. The env-file wrappers, pattern words and file-reading flags: see env-file-wrappers (the env-file rule and its wrappers). Why: those refusals were false alarms.
2. A test-author may write its own session scratchpad (a subagent carries its parent's session id) and paths outside any repo. Product code in a repo, and another session's scratchpad, stay refused. The scratchpad folder name matches without case on Windows. Why: the test-author write denies blocked its own scratch work.
3. A missing guard module makes the guard refuse. The reason names the installer, not the file. This follows gate-hooks-fail-closed (a gate with a missing script refuses the call). Why: a missing module turned every guard off.

Protected by `hooks/test_guard.py` and `hooks/test_wrappers.py`.

## Holes, named

Debts: `env-grep-long-abbrev-unpinned`, `env-file-rule-false-alarms`, `env-flat-crash-allows` and `env-node-env-file-prints` (the env-file holes), `guard-audit-subagent-stop-open` (SubagentStop fails open on a missing guard module).

Kind: process
Home: hooks/guard_env.py
Home: hooks/guard.py
