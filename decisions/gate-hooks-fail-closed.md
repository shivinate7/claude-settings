# Gate hooks fail closed

## The question

When a gate hook cannot run, does the call it guards run?

## The ruling

Owner, 2026-10-12: a gate whose script or python is missing refuses the call. A gate that
times out or crashes does not, because load must never take the setup down, except a missing guard module (guard-audit-high: refuses). A logging
failure never changes a gate's output or exit code: the STE gate and md_sweep log through
`guard_logger` in `lint/_transcript.py`, which catches any Exception. The four command gates in
`settings.json` exit 2 when their script or python is missing. They are PreToolUse
`guard.py`, `ste_gate.py` and `question_outcome.py`, and PermissionRequest
`rm_prompt_answer.py`. For the three PreToolUse gates, exit 2 refuses the call and one stderr
line names the remedy. For `rm_prompt_answer.py`, exit 2 leaves the normal permission prompt
(see Holes). A missing script names `sh install.sh`, or on Windows
`powershell -ExecutionPolicy Bypass -File ./install.ps1`. A missing python says to install Python 3 first. No gate carries `onFailure`: a gate that
times out or crashes lets the call through (see Holes). Owner, 2026-10-14: the PreToolUse `guard.py` hook timeout is 60 s. A command is judged when the guard finishes inside 60 s. Above that it runs unjudged (debt guard-timeout-fails-open). The command length that crosses 60 s is unmeasured.

A fixer crash or timeout in the STE gate keeps plain lint, never a refusal. That is this crash
rule applied to the STE fixer. The STE rewrite ruling is ste-gate-fixes-not-nags, which says the
gate fixes what it can and denies only what remains.

Advisory hooks stay fail-open, because a session must still start, stop and compact. They
are SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, and the SubagentStop guard.
PreToolUse `stall_watch.py` and `sim_boot_record.py` stay advisory too: neither ever
denies, so closing them would only refuse every Bash call when a script is missing. The
SubagentStop guard stays open because exit 2 there sends the agent back to work, and a
missing script would loop it.

## Why

Before this change every wrapper ended `; exit 0`. A missing script, a missing python, a
crash or a timeout let the call through, with no line in guard.log. The guard's refusals
vanished exactly when the guard was broken. Found 2026-10-12 while reading the Claude Code
changelog: `onFailure` landed in 2.1.295.

## What it costs

A machine with `settings.json` but no hooks refuses calls until the hooks are installed.
The refused tools are Bash, PowerShell, Edit, Write, MultiEdit, NotebookEdit, Agent, Task,
Workflow, Skill, AskUserQuestion and two MCP tools the guard matches. The case is a partial
install that linked `settings.json` but not the hooks, or a cloud session that gets the
settings file alone. The refusal
names the remedy. `install.ps1` says so when python is missing.

## What protects it

`hooks/test_wrappers.py`, 39 cases. Each gate wrapper exits 2 with the remedy line on a
missing script and on a missing python. With a script present it execs the script, passes
stdin through, and returns the script's exit code. Advisory entries still exit 0.
No gate, moved or advisory entry carries `onFailure`. The suite is red on a `settings.json`
where a gate carries it.

## Holes, named

Debts: `guard-timeout-fails-open` (a guard that times out lets the call through), `gate-remedy-needs-bash` (the remedy names `sh install.sh`, which Bash cannot run while the guard is missing), `install-sh-no-python-warning` (a Mac without python3 gets no warning), `prompt-hooks-fail-open` (a failed prompt hook lets the call through), `gate-own-errors-fail-open` (a gate's own internal errors exit 0), `gate-exit-7-unprobed` (exit 7 under onFailure block is not probed), `alias-skip-misses-case-forms` (mixed-case and backslash alias paths are not skipped), `install-ps1-counts-store-alias` (install.ps1 passes with only the Store python), `janitor-loop-no-alias-skip` (bin/claude-janitor keeps the old loop with no skip).

## Named limits

- On PermissionRequest, exit 2 leaves the permission flow unchanged and discards stderr. A missing `rm_prompt_answer.py` shows the normal prompt, with no remedy line. This is safe: the gate can only allow, so a prompt is the closed state. `test_wrappers.py` pins exit 2.

Kind: process
Home: hooks/test_wrappers.py
