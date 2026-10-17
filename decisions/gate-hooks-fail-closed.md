# Gate hooks fail closed

## The ruling

Owner, 2026-10-12: a gate whose script or python is missing refuses the call. A gate that times out or crashes does not, because load must never take the setup down, except a missing guard module (`guard-audit-high`: refuses).

- The four command gates in `settings.json` exit 2 when their script or python is missing: PreToolUse `guard.py`, `ste_gate.py` and `question_outcome.py`, and PermissionRequest `rm_prompt_answer.py`.
- For the three PreToolUse gates, exit 2 refuses the call and one stderr line names the remedy. For `rm_prompt_answer.py`, exit 2 leaves the normal permission prompt (see Limit).
- A missing script names `sh install.sh`, or on Windows `powershell -ExecutionPolicy Bypass -File ./install.ps1`. A missing python says to install Python 3 first.
- No gate carries `onFailure`: a gate that times out or crashes lets the call through. The PreToolUse `guard.py` hook timeout is 60 s (owner, 2026-10-14). A command that needs longer runs unjudged. The command length that crosses 60 s is unmeasured.
- A logging failure never changes a gate's output or exit code. The STE gate and md_sweep log through `guard_logger` in `lint/_transcript.py`, which catches any Exception.
- A fixer crash or timeout in the STE gate keeps plain lint, never a refusal. The STE rewrite ruling is `ste-gate-fixes-not-nags`.
- Advisory hooks stay fail-open, because a session must still start, stop and compact: SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, and the SubagentStop guard. PreToolUse `stall_watch.py` and `sim_boot_record.py` stay advisory too, because neither ever denies. The SubagentStop guard stays open because exit 2 there sends the agent back to work, and a missing script would loop it.

Why: wrappers that ended `; exit 0` let the call through on a missing script, so the guard's refusals vanished exactly when the guard was broken.

Cost: a machine with `settings.json` but no hooks refuses Bash, PowerShell, Edit, Write, MultiEdit, NotebookEdit, Agent, Task, Workflow, Skill, AskUserQuestion and two MCP tools. This lasts until the hooks are installed. The refusal names the remedy.

Protected by `hooks/test_wrappers.py`: each gate wrapper exits 2 with the remedy line on a missing script and a missing python. With a script present it execs it, passes stdin through, and returns its exit code. Advisory entries exit 0. The suite is red on a `settings.json` where a gate carries `onFailure`.

## Holes, named

Debts: `guard-timeout-fails-open` (a guard that times out lets the call through), `gate-remedy-needs-bash` (the remedy names `sh install.sh`, which Bash cannot run while the guard is missing), `install-sh-no-python-warning` (a Mac without python3 gets no warning), `prompt-hooks-fail-open` (a failed prompt hook lets the call through), `gate-own-errors-fail-open` (a gate's own internal errors exit 0), `gate-exit-7-unprobed` (exit 7 under onFailure block is not probed), `alias-skip-misses-case-forms` (mixed-case and backslash alias paths are not skipped), `install-ps1-counts-store-alias` (install.ps1 passes with only the Store python), `janitor-loop-no-alias-skip` (bin/claude-janitor keeps the old loop with no skip).

Limit: on PermissionRequest, exit 2 leaves the permission flow unchanged and discards stderr. A missing `rm_prompt_answer.py` shows the normal prompt with no remedy line. This is safe: the gate can only allow, so a prompt is the closed state. `test_wrappers.py` pins exit 2.

Kind: process
Home: hooks/test_wrappers.py
