# An agent outside its home tree must stop

## The ruling

An agent whose worktree is gone must stop and report. `hooks/guard.py` rule 0, `worktree-home`, runs before every other rule.

Why: an agent resumed after the harness removed its worktree (folder and branch) ran in the shared checkout and killed another process. Git cannot tell "never had a worktree" from "worktree was removed", so a record is needed.

- **The home record.** A matched call whose payload carries a valid `agent_id` (`AGENT_ID`, the pattern `janitor/agent_end_reap.py` validates) and whose `cwd` sits inside `<primary>/.claude/worktrees/agent-<agent_id>` writes that path to `<git-common-dir>/agent-homes/<agent_id>`. The common directory is shared by every worktree and outlives any one removal. `primary_checkout` and `git_common_dir` are the only readers of git state this rule needs. The orchestrator's payloads carry no `agent_id`. `session_id` is the same for the orchestrator and its agents. An agent's branch is `worktree-agent-<agent_id>`.
- The write is fail-open. A failed write (a read-only `.git`) leaves that agent unguarded. That is the ceiling.
- **No record.** A call whose `agent_id` never resolves to a home, and whose own `cwd` does not match the worktree shape, is a non-isolated agent. Allow.
- **Outside home, Bash and PowerShell:** the payload `cwd` is not inside the recorded home. This covers a home folder that is gone. A Git Bash `cwd` in the `/c/...` form is read as `C:\...` for this rule only. One exception: a lone move back into the home is allowed. The move is `cd` in Bash, or `cd`, `Set-Location`, `sl`, `chdir` or `pushd` in PowerShell. The home path is its only argument, and the command has no separator.
- **Outside home, Write, Edit, MultiEdit and NotebookEdit:** the target is inside the same clone, under the primary checkout, but outside the recorded home. A target outside the clone, such as a scratchpad file, is allowed.
- **Read and Grep** are always allowed, so the agent can still report (`recovery-must-not-gate-on-its-own-state`).
- **The refusal** never names the recorded home or the call's own path (`git-remedy-never-names-target`). It says the tree is gone or left, to make no further change, and to stop and report to the orchestrator. The matched detail goes to the log.
- **Unreadable is not a hit.** No git, no common directory, or an unreadable record file returns "unknown", which allows (`verification-report-unknown-reads`). A guard that denied on every unreadable state would cry wolf.
- **The predicate is the act** (`predicate-is-the-act`). The rule reads `agent_id`, `cwd` and the write target. The lone-move exception reads the command text only to allow. Any doubt in that read refuses.

Kind: build
Plan: docs/decisions/an-agent-outside-its-home-tree-must-stop.md#the-ruling (all)
