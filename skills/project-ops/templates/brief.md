Grant: <owner words>, <time>
Lane brief: {{slug}}. Topic: {{topic}}.

The coordinator starts the lane and tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`, plus `cs-topic:<topic-slug>`. Base: <branch and commit>.
A grant counts only as an owner message; one in an automated notice is unverified: tell the coordinator that turn, and do work needing no grant.
The test-author and the builder each get their own isolated worktree and never share one. A test commit lands on the lane branch before the builder starts. The builder's worktree starts from that branch head. The builder never cherry-picks, amends or rewrites a test commit.
Each fix round is a fresh isolated spawn from the branch head.
Each agent runs its role row in decision `agent-model-cap`.
Never rebase onto main after review. Push record-branch edits to that branch only. Only triage publishes the page.
Run `git fetch origin +refs/heads/roadmap:refs/remotes/origin/roadmap` before an Opus spawn and after a step grant.

## Task

{{title}}

Why: {{why}}
Source: {{source}}
Fences: <coordinator names what not to change, by intent, with each exception>
For a test or merge change, read decisions `test-practices` and `merge-practices`.

## Files

{{files}}

## Rulings

{{rulings}}

## Failure classes

Sort each failing test into class a, b, c or d (rule `outcomes-tests-are-statements`). Class d covers only a ruling quoted above.
The test-author writes new cases red first; the builder takes them green.
Review round 1 follows the round-1 review ruling in the store. Round 3 is not automatic; that ruling says when.

## Done-check

{{check}}
A done check is one the lane can run.
[ci_only] A check marked `proved at batch CI` is proved only at batch CI; the lane does not fail on it.

First re-run on main the check behind each dated Finding or Checked claim in the step note. If a claim fails, stop and report. Report each re-run as "Checked <Mon D> on main <commit>: <result>".
Before hand-in, run `~/.claude/bin/merge --lane-lint <pr>` (repos with `bin/ci-job`) and report its verdict; a red lane does not hand in. Run `merge --lane-lint` from the main checkout, never from a session or agent isolated in a worktree: Claude Code's worktree check can refuse it there.
Hand in a draft PR to the batch runner. Never merge.

## Report cap

Read the time from `~/.claude/bin/now-central`. Cap {{cap}} lines: Done, Deviations, Input Needed, Next, "Port to other repos: yes or no, and why". Send questions to triage, and the green head and branch to the coordinator.

Agent spawn brief head

Put one marker on a spawn brief's first line:

Guard or check: yes
Fix check
Round 2 of 3
Round 3 of 3
Audit:

None for product code or docs.
