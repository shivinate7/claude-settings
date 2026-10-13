# Gate hooks fail closed

## The question

When a gate hook cannot run, does the call it guards run?

## The ruling

Owner, 2026-10-12: a gate whose script or python is missing refuses the call. A gate that
times out or crashes does not, because load must never take the whole setup down. The four command gates in
`settings.json` exit 2 when their script or python is missing. They are PreToolUse
`guard.py`, `ste_gate.py` and `question_outcome.py`, and PermissionRequest
`rm_prompt_answer.py`. For the three PreToolUse gates, exit 2 refuses the call and one stderr
line names the remedy. For `rm_prompt_answer.py`, exit 2 leaves the normal permission prompt
(see Holes). A missing script names `sh install.sh`, or on Windows
`powershell -ExecutionPolicy Bypass -File ./install.ps1`. A missing python says to install Python 3 first. No gate carries `onFailure`: a gate that
times out or crashes lets the call through (see Holes).

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

- Incident 2026-10-12: with `"onFailure": "block"` on the gates, the guard hook ran past its
  20 s timeout under load. The cause, measured: the wrapper tries `python3` first, and on this
  box that is the Windows Store alias. Through it the guard took over 30 s; through `python`
  it took about 0.4 s. Every Bash, PowerShell and Agent call
  in every session on the machine was refused. The key was removed the same day. So a guard
  that times out lets the call through, with no line in guard.log. Skip the Store alias in the
  wrappers before `onFailure` comes back.

- The remedy names `sh install.sh`, but a missing guard refuses Bash too. The owner runs the
  installer in a terminal of their own.
- A Mac without `python3` gets no warning from `install.sh`; every gated call is then
  refused with the no-python remedy.
- Prompt hooks (Agent, AskUserQuestion, Edit and Write under `decisions/`, SendMessage) can
  deny, but the docs give them no `onFailure`. A failed prompt hook lets the call through.
- On PermissionRequest, the hooks reference says exit 2 leaves the permission flow unchanged
  and discards stderr. So a missing `rm_prompt_answer.py` shows the normal prompt, with no
  remedy line. This is safe: the gate can only allow, so a prompt is the closed state.
  `test_wrappers.py` pins exit 2 for it all the same.
- Errors a gate catches itself fail open. `question_outcome.py` exits 0 when it cannot read
  its input, its state or its model. `guard.py` logs an internal error, then exits 0.
  `ste_gate.py` returns on bad input. `rm_prompt_answer.py` returns on any exception, which
  leaves the prompt.
- With `onFailure: block`, a timeout refused the call (measured in the incident above). Exit 7
  was not probed.
- On this box `python3` resolves to the Windows Store alias. Run from an agent's shell, it
  hung (5 s timeout). The hook context runs it fine: every guard call this session answered.
  If the alias ever hangs in the hook context, every gated call times out and runs unguarded.
- The same change adds `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL: sonnet` beside the subagent
  model (changelog 2.1.296), so workflow agents follow the same default.
