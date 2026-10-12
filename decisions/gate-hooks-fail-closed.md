# Gate hooks fail closed

## The question

When a gate hook cannot run, does the call it guards run?

## The ruling

Owner, 2026-10-12: no. A gate that cannot run refuses the call. The six command gates in
`settings.json` exit 2 when their script or python is missing. They are PreToolUse
`guard.py`, `stall_watch.py`, `ste_gate.py`, `question_outcome.py`, `sim_boot_record.py`,
and PermissionRequest `rm_prompt_answer.py`. One stderr line names the remedy:
`sh install.sh`, or on Windows `powershell -ExecutionPolicy Bypass -File ./install.ps1`.
Each carries `"onFailure": "block"` (Claude Code 2.1.295 and later), so a crash, a timeout or
an unexpected exit code refuses the call too.

Advisory hooks stay fail-open: SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, and
the SubagentStop guard. A session must still start, stop and compact. The SubagentStop guard
stays open because exit 2 there sends the agent back to work, and a missing script would
loop it. Prompt hooks get no `onFailure`: the docs list it for command and HTTP hooks only.

## Why

Before this change every wrapper ended `|| exit 0`. A missing script, a missing python, a
crash or a timeout let the call through, with no line in guard.log. The guard's refusals
vanished exactly when the guard was broken. Found 2026-10-12 while reading the Claude Code
changelog: `onFailure` landed in 2.1.295 on 2026-10-08.

## What it costs

A machine with `settings.json` but no hooks refuses every Bash, Edit and Write call until
the hooks are installed. That is a fresh install before `install.sh`, or a cloud session
that gets the settings file alone. The refusal names the remedy. Whether a runtime older
than 2.1.295 ignores or rejects the `onFailure` key is not documented.

## What protects it

`hooks/test_wrappers.py`. Each gate wrapper exits 2 with the remedy line on a missing
script and on a missing python. Advisory entries still exit 0. `onFailure` is on every gate
and on no advisory entry. The suite is red on main's `settings.json` and green here.

## Holes, named

- The runtime's behaviour on exit 7 and on a timeout was not probed on this box (`claude -p`
  had no login). The docs say both block.
- The Mac's runtime version is unknown; below 2.1.295 only the exit-2 wrapper protects.
- The SubagentStop guard stays fail-open, by design.
