# An agent's own branch never reaches origin

## The ruling

Owner, 2026-11-02: `worktree-agent-*` branches never reach origin. Guard rule `agent-branch-push` refuses a push whose destination is one.

- **Why this rule exists.** Kind: named incident. On 2026-11-02, 32 `worktree-agent-*` branches sat on origin. Each was one agent's own branch, pushed because the agent files said "commit your work to your own branch and push it". The harness names that branch `worktree-agent-<agent_id>` (the layout note in `hooks/guard.py`). Landed 2026-11-02.
- **The cause is fixed first.** `agents/builder.md`, `agents/test-author.md`, `agents/designer.md` and `agents/record-writer.md` say: push only to the branch the brief names, as `git push origin HEAD:<branch>`, never the worktree's own branch. With no branch named, commit only and report.
- **The act.** A `git push` with a destination that starts with `worktree-agent-`, bare or as `refs/heads/worktree-agent-...`. The rule reads where the push goes, not the source: a bare push or a `HEAD` spec resolves through the current branch and `push.default`, as the force-push rule does. It also fires on a forced push.
- **Passes.** A delete (`:name`, `--delete`, `-d`). A fetch. A source with the prefix pushed to another name (`worktree-agent-x:lane`). A name that holds the prefix only inside (`fix-worktree-agent-x`). Quoted text that is no push. A bare push where git cannot name the destination: unknown is not a hit (`verification-report-unknown-reads`).
- **The refusal** cites this record and gives the remedy. It never names the branch (`git-remedy-never-names-target`). The matched push goes to the log.
- **One constant.** `AGENT_BRANCH_PREFIX` in `hooks/guard_push_delete.py` is the only copy of the prefix. No prefix constant existed before this rule; the harness names the branch.
- **An owner override** lifts it (`owner-override`).
- **Cost.** No file written, no process started beyond the push call's own reads. A push with a named, non-`HEAD` destination spends no git call. A bare push, or a `HEAD` or `@` spec, spends one or two git reads. The force-push rule already spent them on a forced push. An unforced push now spends them too.
- **Limits.** `--all` and `--mirror` push every local branch and are not read by this rule. A push from outside the agent's worktree that names the agent branch through a variable cannot be read.
- **Protected by** the `push: ... worktree-agent` cases in `hooks/test_guard.py` (nine refusals, ten passes).

Kind: process
Home: hooks/guard_push_delete.py
