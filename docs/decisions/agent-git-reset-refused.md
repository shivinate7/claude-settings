# An agent's git reset never moves a branch

## The ruling

Rule `agent-git-reset` in `hooks/guard.py` (step 1a) refuses an agent's Bash `git reset` that names a commit other than `HEAD` (rule `shared-trees-no-destructive-git`). Its home is `agent_reset_moves_branch` in `hooks/guard_shared_tree.py`. Layer: coordinator follow-up, 2026-11-12 13:01 CST, step `agent-git-reset-refused`.

- The mistake: a builder ran `git reset --soft` in its own worktree (lane `writer-lists-awaiting-threads`). The discard check judged only the work tree, so `--soft` and `--mixed` passed, as `agent-worktree-discard-is-noted` set out.
- The harm: `--soft` and `--mixed` at another commit move the branch. Commits drop off it, and another session standing on that branch is left on rewritten history. No file changes, so no subject read can see it.
- Who: a call with a valid `agent_id`. The orchestrator and a lane session keep today's verdict.
- Allowed, because an agent needs them: `git reset`, `reset -q`, `reset HEAD`, `reset --soft HEAD`, `reset -- <path>`, `reset HEAD [--] <path>`. Each only unstages.
- Refused: any other plain operand, such as `reset --soft HEAD~1`, `reset HEAD~1`, `reset origin/main`. A lone bare path (`reset f.txt`) is refused too, since git reads a name that is also a revision as a commit.
- Route in the refusal: `git restore --staged <path>` or `git reset -- <path>` to unstage; `git revert <commit>` to undo a commit.
- False alarms: the one normal-work form refused is `git reset <path>` with no `--`. The route above covers it. Measured: 0 other normal forms refused across the 11 cases in the shared-tree family.
- Cost: no process starts; the call is read as text.
- Read inside `sh -c`, `bash -c`, `eval` and nested scripts (`nested_script`, up to 8 texts). The same gap stays open for the shared-tree discard rule (`sh -c 'git reset --hard HEAD~1'` allows); a debt note, not this step.
- Left open, noted:
  - `reset --soft HEAD~1 --keep`: a later mode flag hides the first. Main allows it too.
  - `reset --pathspec-f <file> HEAD~1` refuses though it moves nothing (rare).
  - `reset HEAD~1 -- f.txt` refuses though it moves no branch (rare).
  - A bare `reset .` or `reset src/` refuses. The route is `git reset -- .`.
  - `agent_type` alone also counts as an agent (safe direction).
- `--hard`, `--merge` and `--keep` keep their shared-tree verdicts (`agent-worktree-discard-is-noted`).

Tests that expected `git reset --soft` to pass for an agent were claims. None existed for an agent; the cases that allow it have no `agent_id` and stand for the orchestrator.

Kind: process
Home: hooks/guard_shared_tree.py
