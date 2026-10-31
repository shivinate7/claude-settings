# A kill by pid needs a pid this session started

## The ruling

Rule `shared-trees-no-machine-wide-kill` says to kill only your own processes. `kill` with a literal pid is refused under rule `machine-wide-kill` when the pid is not owned. An owner override lets a kill of a foreign pid through (`owner-override`, the owner's typed override).

- Every Bash command and every hook of one session descends from one process whose command path ends in `claude`. The hook finds it by walking its own parent chain (`ps -o ppid=`, `ps -o comm=`; no list is kept).
- A pid is owned when its own parent chain reaches that process, or when the process is already dead (`ps` exits 1 with no output). Any other `ps` failure is unknown. The `claude` process itself is not owned. Another session's process, and the owner's editor, do not descend from it.
- Owner, 2026-10-10: a pid is also owned when all three hold. Its parent is init (PPID 1). Its cwd is inside `<primary>/.claude/worktrees/agent-<id>`. `agent-<id>.jsonl` exists in this session's agent folder. A pid whose parent is alive stays foreign, also inside the agent worktree. Another session's agent worktree stays foreign.
- Owner, 2026-10-21: ownership by inherited session tag, main session only (ruling below). A pid is also owned when its parent is init (PPID 1) and its exec-time environment holds the whole entry `CLAUDE_CODE_SESSION_ID=<session_id>`, the id the hook payload carries. A prefix, a suffix, another variable's value and argv do not count. `hooks/proc_env.py` reads it (macOS sysctl `KERN_PROCARGS2`, Linux `/proc/<pid>/environ`, no child process), only after the parent walk says foreign, so an allowed kill costs nothing new. Windows is unchanged: no read, so foreign.
- Owner, 2026-10-26: the tag kill is for the main session only. Every agent shares the main session's `session_id`, so the tag cannot tell lane X from lane Y. A call whose payload carries a truthy `agent_id` or `agent_type` keeps the agent-worktree rule alone and fails closed.
- The guard keeps no map of agent ids. It reads the hook payload field `transcript_path` (`<session_id>.jsonl`), and the sibling folder `<session_id>/subagents/` holds `agent-<id>.jsonl` for each agent of that session.
- Pids 0, 1 and -1 are always refused, also under an owner override (owner, 2026-10-18 16:00 CDT) and also when the session root is unknown. A pid group (`-123`) is judged by its leader.
- `kill $(pgrep ...)`, `kill $(pidof ...)` and `pgrep ... | xargs kill` name a target by pattern. They are refused as a kill by name, the same as `pkill`.
- `CLAUDE_GUARD_ROOT_PID` (ASCII digits only) replaces the walk, for the test suite. A command cannot set it, because the harness sets the hook's environment. A `settings.json` `env` block can.

Why: an agent must not stop another agent's server or the owner's editor by pid. Protected by the `kill:` cases in `hooks/test_guard.py` (an orphan in this session's agent worktree, or with this session's tag from the main session, is allowed; the same tag from an agent call, one in another session's worktree, with another session's tag, with none, or with the id only in argv is refused) and the mutations in `hooks/mutate_guard.py`.

## Limits

- `$!`, `$PID`, `%1` and `$(...)` cannot be read, so they pass. The remedy asks for `$!`.
- A lister through a longer pipe (`pgrep x | sort | xargs kill`), process substitution, and pids stored first (`pids=$(pgrep x); kill $pids`) pass.
- A process that reparented to init reads as foreign, unless its cwd is inside one of this session's agent worktrees. In a main-session call, it is also owned when its environment holds this session's tag. A forked shell stub carries no tag (the tool's shell sets it after exec), so a left-behind stub reads foreign. Stop it through the harness.
- Measured on Linux, 2026-10-31: after a stall-watch STALL, the stub shell (PPID 1) holds no tag, and the job under it holds the tag but reads foreign, because its own parent is the stub. A kill of that job stays refused. A wait on it is allowed: `pid_is_session_job` also counts a tag on the pid or on any ancestor below init, and only `bin/wait-pid` asks it (decision stall-watch).
- When no `claude` ancestor or no `ps` exists (Windows, unmeasured), the guard allows. Unknown is not a verdict. `taskkill /PID` and `Stop-Process -Id` pass for the same reason.
- Measured on macOS, 2026-10-26: an orphan an agent's Bash call started holds the tag at exec, equal to the payload `session_id`; no agent-level tag exists. Unmeasured live: the Linux `/proc` read.
- Measured on macOS, 2026-10-26 (claude 2.1.296, PreToolUse on Bash): the main-session payload has `agent_id` and `agent_type` null. Foreground and background general-purpose agent payloads carry both, with the same `session_id`. `transcript_path` is present on both and is the main session's `<session_id>.jsonl`.
- Unmeasured: the payload of a fork agent (the CLI does not offer the type). Also unmeasured: that every agent which left a process has its file on disk, that a resumed agent keeps its id, and the folder layout on Windows and Linux.

Kind: process
Home: hooks/guard_kill.py
