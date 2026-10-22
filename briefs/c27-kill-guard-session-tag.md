Kill guard knows a lane's left-behind server, claude-settings. Goal: a session can stop, by pid, a test server that one of its own lane agents started, after that agent ended, on Mac. A process this session did not start stays refused. No new per-call cost.

Today, checked at 73ed71a: hooks/guard_kill.py foreign_pid_kill allows a kill by pid only when the parent chain reaches this session's claude process. When an agent ends, macOS hands its server to init (PPID 1), so the guard calls it foreign. The one exception, in_own_agent_worktree, needs the cwd inside .claude/worktrees/agent-<id> AND <session>/subagents/agent-<id>.jsonl. Lane agents work in scratchpad folders, and workflow agents keep their records under subagents/workflows/, so it never matches them. Decision a-kill-by-pid-needs-an-owned-pid lists this as a known limit.

First check, before any code: on the owner's Mac, start `sleep 600 &` from a Bash call inside a subagent, let the subagent end, and confirm three things. (1) The sleep's PPID is 1. (2) Its environment holds CLAUDE_CODE_SESSION_ID equal to the hook payload's session_id. Read it the way lane 1 will. (3) Where the subagent's record landed under subagents/. If (2) fails, stop and report; do not fall back to path rules.

Lane 1, ownership by inherited tag. In guard_kill.py add one check beside in_own_agent_worktree: a pid is owned when its PPID is 1 and its environment holds CLAUDE_CODE_SESSION_ID exactly equal to this session's id (session_id_of, from the payload). Read the environment without a child process where you can: Linux /proc/<pid>/environ; Mac sysctl KERN_PROCARGS2 through ctypes, which returns argv and env separately, so a matching string in argv does not count. Match a whole NAME=value entry, never a substring. Any read failure means foreign. Read it only on the path that already found the pid foreign, so an allowed kill costs nothing new. Keep the worktree exception. Windows stays as today (unknown, allowed).

Lane 2, the reaper uses the same test. janitor/agent_end_reap.py only looks under .claude/worktrees/agent-<id>, so a scratchpad lane's server runs until a full sweep. On SubagentStop, also stop each orphaned process whose environment holds this session's id and whose cwd sits in this session's scratchpad, with the reaper's other reads unchanged. If one shared helper serves both files, give it one home (shared module) and import it from both.

Lane 3, one brief line. Wherever the lane brief template lives, add: a lane stops each server it started before it ends, by $! from the same call or through the harness.

Tests, red on main and green on the fix: a PPID-1 process carrying this session's id is allowed; the same process carrying another session's id is denied; one with no tag is denied; one whose argv, not env, holds the id is denied; pids 0, 1, -1 stay denied. Add a mutant in hooks/mutate_guard.py that drops the exact-match check, and show a test kills it. Update the decision a-kill-by-pid-needs-an-owned-pid in place: one dated owner line, Oct 21, and fix the Limits list.

Overlap: PR #557 (refuse a recursive delete of a parent folder) edits hooks/guard.py, delete section only. This work should not need guard.py; if it does, rebase on #557 first.

Report: the first-check results, the diff size per file, test names, and the decision's before and after text.
