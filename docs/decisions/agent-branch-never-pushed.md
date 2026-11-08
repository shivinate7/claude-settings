# An agent's own branch never reaches origin

## The ruling

Owner, 2026-11-02: `worktree-agent-*` branches never reach origin. Guard rule `agent-branch-push` refuses a push whose destination is one.

- **Why this rule exists.** Kind: named incident. On 2026-11-02, 32 `worktree-agent-*` branches sat on origin. Each was one agent's own branch, pushed because the agent files said "commit your work to your own branch and push it". The harness names that branch `worktree-agent-<agent_id>` (the layout note in `hooks/guard.py`). Ruled 2026-11-02.
- **The cause is fixed first.** `agents/builder.md`, `agents/test-author.md`, `agents/designer.md` and `agents/record-writer.md` say: push only to the branch the brief names, as `git push origin HEAD:<branch>`, never the worktree's own branch. With no branch named, commit only and report.
- **The act.** A `git push` with a destination that starts with `worktree-agent-`, bare or as `refs/heads/worktree-agent-...`. The rule reads where the push goes, not the source: a bare push or a `HEAD` spec resolves through the current branch and `push.default`, as the force-push rule does. A `$` or backtick destination is the one place the source decides (see Limits). It also fires on a forced push.
- **Passes.** A dry run (`--dry-run`, `-n`). A delete (`:name`, `--delete`, `-d`). A fetch. A source with the prefix pushed to another name (`worktree-agent-x:lane`). A name that holds the prefix only inside (`fix-worktree-agent-x`). Quoted text that is no push. A bare push where git cannot name the destination: unknown is not a hit (`verification-report-unknown-reads`).
- **The refusal** cites this record and gives the remedy. It never names the branch (`git-remedy-never-names-target`). The matched push goes to the log.
- **One constant.** `AGENT_BRANCH_PREFIX` in `hooks/guard_push_delete.py` is the only copy of the prefix. No prefix constant existed before this rule; the harness names the branch.
- **An owner override** lifts it (`owner-override`).
- **Cost.** No file written, no process started beyond the push call's own reads. A push with a named, non-`HEAD` destination spends no git call. A bare push, or a `HEAD` or `@` spec, spends one to three git reads. A `$` or backtick destination with another source spends one, to read the current branch. The force-push rule already spent them on a forced push. An unforced push now spends them too.
- **Archive stays allowed.** `archive/worktree-agent-*` is no hit: its name does not start with the prefix. Rule `shared-trees-archive-then-delete` pushes an unmerged branch there before it is deleted (lane ruling, 2026-11-02).
- **No brief branch.** An agent with no branch in its brief keeps its commits local and reports. It pushes nowhere.
- **Limits.** `--all` and `--mirror` push every local branch. From an agent worktree the bare destination is its own branch, so the rule refuses them. From any other checkout `--all` and its alias `--branches` ask under main's push rules (`push_ask_hit`), and `--mirror` asks under the force-push rule. A destination that holds `$` or a backtick (`$BR`, `$(...)`) is shell text the guard cannot read. From an agent worktree, with a source other than `HEAD` or `@`, the rule refuses it. From any other checkout, or with a `HEAD` or `@` source (`HEAD:$BRANCH`), it stays unread and passes. A trailing `cd` after the push (`git push ...; cd x`) moves the folder the guard reads. A `*` or `refs/heads/*` destination from an agent checkout is unread.
- **Protected by** the `agent push:` cases in `hooks/test_guard.py` (16 refusals, 23 passes) and its cost check, which shows a named destination spends no git read.

Kind: process
Home: hooks/guard_push_delete.py
