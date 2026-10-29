# An agent outside its home tree must stop

## The ruling

Each session writes only inside its own checkout. An agent whose worktree is gone must stop and report. A top-level session whose worktree is gone makes a new one before it writes. `hooks/guard.py` rule 0 holds all three parts and runs before every other rule.

Why, three events:

- An agent resumed after the harness removed its worktree (folder and branch) ran in the shared checkout and killed another process. Date not recorded.
- Incident 2026-09-06, a write into another checkout: a session wrote into a different checkout of the same clone. `worktree-home` judges only isolated agents, so it could not see a top-level session or one started in `.claude/worktrees/<x>`.
- Banchi notes-folder refusal, 2026-10-27 (outbox `banchi-guard-shared-notes`, Banchi's guard blocks shared notes): Banchi's own guard clause `tree` in `scripts/guard-shell.py` refuses every write outside the checkout, so it refused `~/Library/Application Support/Claude-Work/side-session-notes/`, where the Claude app keeps side-session notes. A folder in no checkout must stay writable.

Risk: incident (2026-09-06). `other-checkout` landed 2026-10-28.

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
- **The common git directory passes.** `<primary>/.git` is shared by every checkout, so a linked worktree may write `.git/info/exclude`.
- **Removing a worktree by hand is refused.** `rm -rf .claude/worktrees/<x>` from the primary is a write into another checkout. The refusal names `git worktree remove` and the janitor sweep, the proper tools.
- **Tools.** Write, Edit, MultiEdit and NotebookEdit targets, and the shell write targets that frozen-path reads (`_shell_write_hit`: a redirect, a mutating command, `sed -i`). A relative shell target resolves against the folder a leading `cd` moved to (`dir_before_segment`), or against `cwd` when that folder cannot be told. A shell read, or a git command run with `-C` into another checkout, is no write here.
- **Ceiling.** A target named through a variable the scan cannot resolve, `$(...)`, or an interpreter (`python -c`) is not seen, as for frozen-path.
- **Cost.** At most one `git worktree list --porcelain -z` per call. A Read or Grep spends none. A shell command spends none unless it holds a `>`, a mutating command or `sed` once redirects onto a stream (`2>&1`) or `/dev/null` are dropped. A call whose `cwd` has no `.git` at or above it spends none (a stat walk). No file, log or process is added. `worktree_home_cross_checkout_cost_case` counts the spawns.
- **An owner override lifts it.** The owner may mean the write. It has its own rule id so that `worktree-home` stays outside every override.

### `session-home`: a top-level session whose worktree is gone makes a new one

Owner ask, 2026-10-29 16:49 CDT: a resumed top-level session whose worktree was removed ran in the primary checkout. Risk: likely (owner-reported). Landed 2026-10-29.

- **The record.** A call with no `agent_id` whose `cwd` sits in `<primary>/.claude/worktrees/<name>` writes that path to `<primary>/.git/session-homes/<session_id>`, only when the record is missing or differs. A call with an `agent_id` never writes it: agents share the session's `session_id`. A call whose `cwd` sits in an agent's worktree, `<primary>/.claude/worktrees/agent-<agent_id>`, never writes it either: that is the session inspecting an agent's tree.
- **A deliberate exit clears it.** An ExitWorktree call with no `agent_id`, from any `cwd`, deletes a record whose folder still stands. ExitWorktree is in the guard's PreToolUse matcher for this reason. An ExitWorktree while the record is lost clears nothing.
- **The write is atomic.** A temp file in the same folder, then a rename, so no reader sees half a path.
- **The act.** No `agent_id`, a non-empty record whose folder is gone, `cwd` in the primary checkout, and one of:
  - a Write, Edit, MultiEdit or NotebookEdit target, or a shell write as `_shell_write_hit` reads it, in the primary checkout or under the lost home path;
  - a git command run in the primary that changes its files or branch: checkout, switch, pull, merge, commit, rebase, restore, reset, stash, cherry-pick, revert, am, apply. The owner's ask is "refuse writes in the primary checkout", and these write it.
- **Passes.** A target under `<primary>/.git/`, or outside the clone. Read, Grep, and a shell call that writes no file (`git fetch`, `git status`, `git log`, `git diff`, `git branch <name>`, `git worktree add`), so recovery never depends on the lost state. A git command run with `-C` in a live worktree. A git command whose folder is a shell variable (`cd "$WT" && git commit`, `git -C "$WT" commit`): the folder is unknown. A write inside a new worktree, which also rewrites the record.
- **No record passes.** A fresh session, and one that never entered a worktree, are unchanged.
- **Resume notice.** `hooks/session_start.sh`, on `source` `resume` with a record whose folder is gone, prints one line: make a new worktree with the EnterWorktree tool before any write. EnterWorktree branches from origin's default branch by default (`worktree.baseRef` "fresh").
- **The refusal** names EnterWorktree, never the lost path (`git-remedy-never-names-target`).
- **An owner override lifts it** (`owner-override`). A top-level session is the owner's own, so the owner may mean the write.
- **Cost.** No git spawn beyond what the call already spends: the primary is found by path shape and a stat walk. Files written: one record per session that entered a worktree, rewritten only when its worktree changes, deleted at ExitWorktree. Nothing else deletes it. `session_home_*_case` counts the spawns.
- **Premises.** A resume keeps the `session_id` unless `--fork-session` is passed (CLI reference, read; unmeasured live). A resume whose worktree is gone starts in the folder Claude was launched from (worktrees docs, read).
- **Limits.** A session whose `cwd` is in no checkout, which then runs `cd <primary> && <write>`, is not judged. A lane lost before its first guarded call (Read and Grep only) left no record. A worktree removed by hand with `git worktree remove`, without ExitWorktree, leaves the record: primary writes are refused until a new worktree or an override. A cloud container reclaim gives a fresh clone with no record, so a resumed cloud session is allowed in its fresh, unshared primary.

### All three parts

- **Read and Grep** are always allowed, so a session can still report (`verification-recovery-independent-of-state`).
- **The refusal** never names the target or the home (`git-remedy-never-names-target`). The matched detail goes to the log.
- **Unreadable is not a hit.** No git, no common directory, an unreadable record, or a `cwd` in no checkout allows (`verification-report-unknown-reads`).
- **The predicate is the act** (`predicate-is-the-act`). The rule reads `agent_id`, `cwd` and the write target.

Kind: build
Plan: docs/decisions/an-agent-outside-its-home-tree-must-stop.md#the-ruling (all)
