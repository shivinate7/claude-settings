# Gate hooks fail closed

## The question

When a gate hook cannot run, does the call it guards run?

## The ruling

Owner, 2026-10-12: no. A gate that cannot run refuses the call. The four command gates in
`settings.json` exit 2 when their script or python is missing. They are PreToolUse
`guard.py`, `ste_gate.py` and `question_outcome.py`, and PermissionRequest
`rm_prompt_answer.py`. One stderr line names the remedy. A missing script names
`sh install.sh`, or on Windows `powershell -ExecutionPolicy Bypass -File ./install.ps1`. A
missing python says to install Python 3 first. Each gate carries `"onFailure": "block"`
(Claude Code 2.1.295 and later), so a crash, a timeout or an unexpected exit code refuses
the call too.

Advisory hooks stay fail-open, because a session must still start, stop and compact. They
are SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, and the SubagentStop guard.
PreToolUse `stall_watch.py` and `sim_boot_record.py` stay advisory too: neither ever
denies, so closing them would only refuse every Bash call when a script is missing. The
SubagentStop guard stays open because exit 2 there sends the agent back to work, and a
missing script would loop it.

## Why

Before this change every wrapper ended `|| exit 0`. A missing script, a missing python, a
crash or a timeout let the call through, with no line in guard.log. The guard's refusals
vanished exactly when the guard was broken. Found 2026-10-12 while reading the Claude Code
changelog: `onFailure` landed in 2.1.295.

## What it costs

A machine with `settings.json` but no hooks refuses calls until the hooks are installed.
The refused tools are Bash, PowerShell, Edit, Write, MultiEdit, NotebookEdit, Agent, Task,
Workflow, Skill and AskUserQuestion, plus every PermissionRequest prompt. That is a fresh install
before `install.sh`, or a cloud session that gets the settings file alone. The refusal
names the remedy. `install.ps1` says so when python is missing.

## What protects it

`hooks/test_wrappers.py`, 39 cases. Each gate wrapper exits 2 with the remedy line on a
missing script and on a missing python. With a script present it execs the script, passes
stdin through, and returns the script's exit code. Advisory entries still exit 0.
`onFailure` is on every gate and on no advisory entry. The suite is red on main's
`settings.json`.

## Holes, named

- Prompt hooks (Agent, AskUserQuestion, Edit and Write under `decisions/`, SendMessage) can
  deny, but the docs give them no `onFailure`. A failed prompt hook lets the call through.
- `question_outcome.py` exits 0 when it cannot read its input, its state or its model. It
  is a gate that fails open inside its own script.
- The runtime's behaviour on exit 7 and on a timeout was not probed (`claude -p` had no
  login on this box). The docs say both block.
- On this box `python3` resolves to the Windows Store alias. Run from an agent's shell, it
  hung (5 s timeout). The hook context runs it fine: every guard call this session answered.
  If the alias ever hangs in the hook context, every gated call times out and is refused.
- The Mac's runtime version is unknown; below 2.1.295 only the exit-2 wrapper protects.
- The same change adds `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL: sonnet` beside the subagent
  model (changelog 2.1.296), so workflow agents follow the same default.
