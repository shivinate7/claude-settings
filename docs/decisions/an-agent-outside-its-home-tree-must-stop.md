# An agent outside its home tree must stop

## The ruling

Each session writes only inside its own checkout. An agent whose worktree is gone must stop and report. `hooks/guard.py` rule 0 holds both parts and runs before every other rule.

Why: an agent resumed after the harness removed its worktree (folder and branch) ran in the shared checkout and killed another process (incident 2026-09-06). A session in one checkout also wrote into another checkout of the same clone, and the agent-only rule did not see it. The Banchi notes-folder refusal showed the other edge: a notes folder outside every checkout must stay writable.

Risk: incident (2026-09-06, and the notes-folder refusal). `other-checkout` landed 2026-10-28.

### `worktree-home`: an agent stays in its recorded home

- **The home record.** A call whose payload carries a valid `agent_id` (`AGENT_ID`, the pattern `janitor/agent_end_reap.py` validates) and whose `cwd` sits inside `<primary>/.claude/worktrees/agent-<agent_id>` writes that path to `<git-common-dir>/agent-homes/<agent_id>`. The common directory is shared by every worktree and outlives any one removal. The orchestrator's payloads carry no `agent_id`. An agent's branch is `worktree-agent-<agent_id>`.
- The write is fail-open. A failed write (a read-only `.git`) leaves that agent unguarded. That is the ceiling.
- **No record.** An `agent_id` that never resolves to a home, with a `cwd` not in the worktree shape, is a non-isolated agent. This part allows it.
- **Bash and PowerShell:** the payload `cwd` is not inside the recorded home. This covers a home folder that is gone. A Git Bash `cwd` in the `/c/...` form is read as `C:\...`. One exception: a lone move back into the home is allowed (`cd`, or in PowerShell `Set-Location`, `sl`, `chdir`, `pushd`), with the home path as its only argument and no separator.
- **Write, Edit, MultiEdit and NotebookEdit:** the target is under the primary checkout but outside the recorded home.
- **No override lifts it** (`owner-override`, owner 2026-10-18 18:37 CDT).

### `other-checkout`: no session writes into another checkout

- **Who.** Every session: the top-level session, a session started in `.claude/worktrees/<x>`, and every agent.
- **The act.** A write whose resolved target sits in a checkout of the clone other than the checkout that holds `cwd`. The checkouts are the primary and each linked worktree. A nested worktree under `<primary>/.claude/worktrees/` owns its own files; the deepest checkout that holds a path owns it. So primary to nested worktree, worktree to primary, and worktree to sibling are refused. A write inside the call's own checkout passes.
- **Outside the clone passes.** A scratchpad, `~/.claude`, or a notes folder such as `~/Library/Application Support/Claude-Work/side-session-notes/` is in no checkout.
- **Tools.** Write, Edit, MultiEdit and NotebookEdit targets, and the shell write targets that frozen-path reads (`_shell_write_hit`: a redirect, a mutating command, `sed -i`). A shell read, or a git command run with `-C` into another checkout, is no write here.
- **Cost.** One `git worktree list --porcelain -z` per write call. A shell command with no `>`, mutating command or `sed` spends none. No file, log or process is added.
- **An owner override lifts it.** The owner may mean the write. It has its own rule id so that `worktree-home` stays outside every override.

### Both parts

- **Read and Grep** are always allowed, so a session can still report (`verification-recovery-not-gated-on-own-state`).
- **The refusal** never names the target or the home (`git-remedy-never-names-target`). The matched detail goes to the log.
- **Unreadable is not a hit.** No git, no common directory, an unreadable record, or a `cwd` in no checkout allows (`verification-report-unknown-reads`).
- **The predicate is the act** (`predicate-is-the-act`). The rule reads `agent_id`, `cwd` and the write target.

Kind: build
Plan: docs/decisions/an-agent-outside-its-home-tree-must-stop.md#the-ruling (all)
