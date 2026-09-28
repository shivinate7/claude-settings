# An agent outside its home tree must stop

## The incident

An agent was resumed after the harness had already removed its worktree.
It then ran in the shared checkout, ran a reap there, and killed another
process. The harness had deleted both the worktree folder and the
worktree branch. Nothing in the tree told the agent, or the guard, that
its home was gone.

## Measured facts

Probe on 2026-09-27, macOS, one Explore agent with `isolation: 'worktree'`:

- A PreToolUse payload from a subagent carries `agent_id` (for example
  `a64a7f84210a8721d`) and `agent_type`. The orchestrator's own payloads
  carry no `agent_id`.
- `session_id` is the same for the orchestrator and its agents. It never
  tells them apart.
- The subagent's `cwd` was `<primary>/.claude/worktrees/agent-<agent_id>`.
  Branch name: `worktree-agent-<agent_id>`.
- When the harness auto-removes an unchanged worktree, it deletes the
  folder AND the branch. Git alone cannot tell "never had a worktree"
  from "worktree was removed". A record is needed.

Unmeasured: Windows, and the Write/Edit payload shape on this machine.
Both are covered in hooks/test_guard.py by fixture, not by a live probe.

## The rule

hooks/guard.py, rule 0, `worktree-home`, runs before every other rule.

**The home record.** On any matched call whose payload carries a valid
`agent_id` (`AGENT_ID`, the same pattern janitor/agent_end_reap.py
already validates against) and whose `cwd` sits inside
`<primary>/.claude/worktrees/agent-<agent_id>`, the guard writes that
path. It writes to `<git-common-dir>/agent-homes/<agent_id>`. The common
directory is shared by every worktree of the clone. It outlives any one
worktree's removal, so the record survives exactly the loss this rule
exists for. `primary_checkout` and `git_common_dir` (refactored out of
the same `_common_dir` read, so the two never drift apart) are the only
readers of git state this rule needs. Nothing here copies them.

**No record.** A call whose `agent_id` never resolves to a home, and
whose own `cwd` does not match the worktree shape either, is a
non-isolated agent. Nothing changes for it: allow.

**Outside home.**

- Bash / PowerShell: the payload `cwd` is not inside the recorded home.
  This covers the home folder being gone entirely. A resolved path
  compares correctly whether or not it still exists.
- Write / Edit / MultiEdit / NotebookEdit: the target sits inside the
  same clone, under the primary checkout, but outside the recorded home.
  A target outside the clone, such as a scratchpad file, is allowed. This
  rule protects the shared checkout and other agents' trees. A
  scratchpad file cannot touch either one.
- Read / Grep: always allowed. The agent must still be able to read and
  report (decisions/recovery-must-not-gate-on-its-own-state.md: a
  recovery control must not depend on the state it recovers).

**The refusal** never names the recorded home or the call's own path
(CLAUDE.md, "a refusal's printed remedy never names the forbidden
target"). It says the tree is gone or left, to make no further change,
and to stop and report to the orchestrator. The matched detail still goes
to the log, same as every other rule here.

**Unreadable is not a hit.** No git, no common directory, or an
unreadable record file all return "unknown", which allows
(decisions/liveness-read-is-platform-specific-and-unreadable-is-not-death.md).
A guard that denied on every unreadable state would go red on machines
this repo has never measured. CLAUDE.md's cry-wolf rule says that guard
then gets ignored.

**The predicate is the act**, not the command's text
(decisions/predicate-is-the-act.md). This rule reads `agent_id`, `cwd`,
and the write target only. No command string is matched.

## What reopens it

- A harness payload shape that stops carrying `agent_id`, or that carries
  a `cwd` this rule cannot resolve.
- A worktree naming scheme other than `agent-<agent_id>` under
  `.claude/worktrees/`.
- A confirmed case on Windows or in a Write/Edit payload that disagrees
  with the shapes recorded here.
