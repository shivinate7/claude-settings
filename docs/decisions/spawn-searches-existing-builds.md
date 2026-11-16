# A build spawn names the prior work it searched

## The ruling

Rule `spawn-searches-existing-builds` in `hooks/guard.py` refuses a build spawn whose brief has no `Prior work:` line with text after it. The reader and the lane forms are `prior_work_named` and `prior_work_lane_hit` in `hooks/guard_merge.py`. The Agent form is `prior_work_agent_hit` in `hooks/guard.py`, called after `brief_claim_hit`. The rule extends the families `role-model` (the Agent spawns) and `lane-step-dup-pr` (the lane starts and briefs). It adds no family.

- The mistake (2026-11-15 CST): sessions built what already existed. On 2026-11-15 they rebuilt the removal act of the per-lane merge switch (act 4 of R42 part 2, decision `all-repos-switch-together`), the lane-merge PRs, and two pull requests: #2842 (drop the STE001 sentence cap) and #2845, the PR ledger in merge --reviewed. A builder ran to a diff, and only then did anyone find the earlier PR or branch.
- The harm: a duplicate lane costs a full build, a review and a merge. The same step then has two PRs that clash. The owner has to sort out which one stands.
- The owner ruling (18:18 CST, 2026-11-15): before it spawns a build, every standing session searches open and closed pull requests, branches and main for an existing build. A hook enforces it.
- Read three calls. First, an Agent or Task call to a builder or a test-author (its prompt, role as in `BRIEF_CLAIM_ROLES`). Second, a `create_session` that tags a lane (its prompt). Third, a `send_message` whose first non-blank line after any Grant line starts `Lane brief:` (its message). A reviewer, an Explore and every other role pass.
- The line: `Prior work: #N (state) | <branch> | none found`, on a line of its own, after optional markdown lead characters. The marker matches without case. A bare `Prior work:` line counts as none, and so does a line holding only an unfilled `<placeholder>`. The colon may sit outside bold (`**Prior work**: x`), and a numbered-list lead (`1. `) is allowed. A line inside a fence does not count. Each call is judged by its own text, so an earlier spawn's line grants nothing.
- The check reads the brief only. It does not ask GitHub whether the named pull request or branch exists, so it proves that the search was named, not that it was done.
- The override lifts it (`owner-override`). It is not in `never_lifted`: the owner may mean the spawn as it stands.
- Cost: a line scan of the brief text. No git read, no file written, no process, no log line beyond the refusal's own.

## Known holes

- A Workflow `agent()` spawn is not read. Only Agent, Task, `create_session` and the lane brief are.
- Any text after the colon passes, so `Prior work: n/a` passes.
- A lane brief whose first line is not `Lane brief:` is not read.

Protected by the `prior-work:` cases in `tests/guard/s40805-role-model.py` and `tests/guard/s42910-lane-step-pr.py`, red before the rule existed.

Kind: process
Home: hooks/guard_merge.py
