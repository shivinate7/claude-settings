# Guard rules from the 2026-10-13 audit

## The question

Which guard refusals are false alarms or gaps? What does the guard do when one of its modules is missing?

## The ruling, 2026-10-13

Owner, 2026-10-13 14:40, on an audit by the oversight session. Three rules:

1. The env-file rule looks through the `verdict`, `timeout`, `time`, `do`, `python`, `python3` and `py` wrappers to the real runner. A grep, sed or awk pattern or program is never read as an env file. The file-reading flags still refuse: `-f`, `--file`, `sed -f` and `awk -f`.
2. A test-author may write its own session scratchpad. A subagent carries its parent's session id. A test-author may also write to paths outside any repo. Product code in a repo, and another session's scratchpad, stay refused. The scratchpad folder name matches without case on Windows.
3. A missing guard module makes the guard refuse. The reason names the installer, not the file. This follows gate-hooks-fail-closed (a gate with a missing script refuses the call).

## Why

Measured by the oversight session's audit:

- About 690 env-file denies a week. Since 2026-10-12, 25 were for `grep '.*'` and 7 for `do`.
- 403 test-author write denies a week.
- 121 guard-crash lines from 12:03 to 12:44 on 2026-10-13, with every guard off.

## What protects it

`hooks/test_guard.py` and `hooks/test_wrappers.py`. The red cases were committed first, in 962eafc and 2d4e032.

## Holes, named

- `grep --regex=` style abbreviations of `--regexp`, `--expression` and `--source` are a hole.
- `ag -f` and `ack -f` now refuse. In those tools `-f` is a boolean, so this is a false alarm.
- `grep -r --exclude=.env` and `rg -t py .env` are false alarms.
- On SubagentStop, a missing module still fails open. One log line records it.
- A runtime crash in `_env_flat` allows the call.
- An `awk -v` value holding a glob is cleared.

Kind: process
Home: hooks/guard_env.py
Home: hooks/guard.py
