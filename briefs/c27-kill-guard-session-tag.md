# c27: kill guard knows a lane's left-behind server (Mac session)

Paste the block below, whole, into one fresh claude-settings session on the Mac. Re-checked by the
advisor against claude-settings main 149f4bc5, Oct 26.

```
Kill guard knows a lane's left-behind server (c27), claude-settings, on this Mac. Goal: a session can stop, by pid, a test server that one of its own lane agents started, after that agent ended. A process this session did not start stays refused. No new per-call cost.

Today (main 149f4bc5): hooks/guard_kill.py foreign_pid_kill(tokens, transcript) allows a kill by pid only when the parent chain reaches this session's claude process. When an agent ends, macOS hands its server to init (PPID 1), so the guard calls it foreign. The one exception, in_own_agent_worktree, needs the cwd inside .claude/worktrees/agent-<id> AND <session>/subagents/agent-<id>.jsonl. Lane agents work in scratchpad folders, and workflow agents keep records under subagents/workflows/, so it never matches them. Decision a-kill-by-pid-needs-an-owned-pid lists this as a known limit.

1. First check, before any code. Start `sleep 600 &` from a Bash call inside a subagent, let the subagent end, and confirm: (a) the sleep's PPID is 1; (b) its environment holds CLAUDE_CODE_SESSION_ID equal to the hook payload's session_id, read the way step 2 will; (c) where the subagent's record landed under subagents/. If (b) fails, stop and report. Do not fall back to path rules.

2. Ownership by inherited tag. In guard_kill.py, beside in_own_agent_worktree: a pid is owned when its PPID is 1 and its environment holds CLAUDE_CODE_SESSION_ID exactly equal to this session's id. guard.py already reads the id with session_id_of(payload); pass it into foreign_pid_kill. Read the environment with no child process: Mac sysctl KERN_PROCARGS2 through ctypes (argv and env come back separately, so a match in argv does not count); Linux /proc/<pid>/environ. Match a whole NAME=value entry, never a substring. Any read failure means foreign. Read it only on the path that already found the pid foreign, so an allowed kill costs nothing new. Keep the worktree exception. Windows stays as today.

3. The reaper uses the same test. janitor/agent_end_reap.py only looks under .claude/worktrees/agent-<id>. On SubagentStop, also stop each orphaned process whose environment holds this session's id and whose cwd sits in this session's scratchpad; its other reads stay. One shared helper, one home, imported from both files. Update decision agent-end-reap-stops-what-a-finished-agent-left in place.

4. One brief line. Where lane briefs are written (find the home; add no second one): a lane stops each server it started before it ends, by $! from the same call or through the harness.

Tests, red on main and green on the fix: a PPID-1 process carrying this session's id is allowed; the same with another session's id is denied; one with no tag is denied; one whose argv, not env, holds the id is denied; pids 0, 1 and -1 stay denied. Add a mutant in hooks/mutate_guard.py that drops the exact-match check, and show a test kills it. Update decision a-kill-by-pid-needs-an-owned-pid in place: one dated owner line (Oct 21, ownership by inherited session tag) and fix its Limits list.

Ship as one PR under the repo's normal review and merge rules. Report: the first-check results, diff size per file, test names, the two decisions' before and after text, and the PR.
```
