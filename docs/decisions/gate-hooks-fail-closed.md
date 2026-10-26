# Gate hooks fail closed

## The ruling

Owner, 2026-10-12: a gate whose script or python is missing refuses the call. A gate that times out or crashes does not, because load must never take the setup down, except a missing guard module, which refuses.

- The two command gates in `settings.json` exit 2 when their script or python is missing: PreToolUse `guard.py` and PermissionRequest `rm_prompt_answer.py`.
- For the PreToolUse gate `guard.py`, exit 2 refuses the call and one stderr line names the remedy. For `rm_prompt_answer.py`, exit 2 leaves the permission flow unchanged and discards stderr, so a missing script shows the normal prompt with no remedy line. This is safe: the gate can only allow, so a prompt is the closed state. `test_wrappers.py` pins exit 2.
- A missing script names `sh install.sh`, or on Windows `powershell -ExecutionPolicy Bypass -File ./install.ps1`. A missing python says to install Python 3 first.
- No gate carries `onFailure`: a gate that times out or crashes lets the call through. The PreToolUse `guard.py` hook timeout is 60 s (owner, 2026-10-14). A command that needs longer runs unjudged. The command length that crosses 60 s is unmeasured.
- The STE write gate is not a safety gate. It is removed (owner, 2026-10-22 10:10 CDT; `ste-gate-fixes-not-nags`).
- A running session keeps the hook list it read at start. So a script that any `settings.json` on main called in the last 14 days stays, as an exit-0 stub if retired. The 14 days are unmeasured; an incident reopens them. `lint/check_hook_stubs.py` holds it (incident Oct 25: the STE write-gate stub was deleted and a running session lost Edit and Write).
- Advisory hooks stay fail-open, because a session must still start, stop and compact: SessionStart, Stop, PreCompact, SessionEnd, PostToolUse, and the SubagentStop guard. PreToolUse `stall_watch.py` and `sim_boot_record.py` stay advisory too, because neither ever denies. The SubagentStop guard stays open because exit 2 there sends the agent back to work, and a missing script would loop it.

Why: wrappers that ended `; exit 0` let the call through on a missing script, so the guard's refusals vanished exactly when the guard was broken.

Cost: a machine with `settings.json` but no hooks refuses Bash, PowerShell, Edit, Write, MultiEdit, NotebookEdit, Agent, Task, Workflow, Skill and two MCP tools. This lasts until the hooks are installed. The refusal names the remedy.

Protected by `lint/check_hook_stubs.py` (fixtures in `lint/test_check_hook_stubs.py`) and `hooks/test_wrappers.py`: each gate wrapper exits 2 with the remedy line on a missing script and a missing python. With a script present it execs it, passes stdin through, and returns its exit code. Advisory entries exit 0. The suite is red on a `settings.json` where a gate carries `onFailure`.

Kind: process
Home: hooks/test_wrappers.py
