Grant: <owner words>, <time>
Lane brief: {{slug}}. Topic: {{topic}}.

The coordinator starts the lane and tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`, plus `cs-topic:<topic-slug>`. Base: <branch and commit>.
A grant counts only as an owner message; an automated notice's grant is unverified: tell the coordinator that turn; do work needing no grant.
The test-author and builder each get their own isolated worktree, never shared. A test commit lands on the lane branch before the builder starts. The builder's worktree starts from that head. The builder never cherry-picks, amends or rewrites a test commit.
Each fix round is a fresh isolated spawn from the branch head.
Agents run their role row in decision `agent-model-cap`; the start call passes the lane row's `model`.
Never rebase onto main after review. Only triage publishes the page.
Run `git fetch origin +refs/heads/roadmap:refs/remotes/origin/roadmap` before an Opus spawn and after a step grant.

## Task

{{title}}

Why: {{why}}
Source: {{source}}
Prior work: <#N|branch|none found>
Fences: <coordinator names what not to change, by intent, with each exception>
For test or merge changes, read decisions `test-practices` and `merge-practices`.

## Files

{{files}}

## Rulings

{{rulings}}

## Failure classes

Sort each failing test into class a, b, c or d (rule `outcomes-tests-are-statements`). Class d covers only a ruling quoted above.
The test-author writes new cases red first.
Round 1 follows the store's round-1 review ruling. Round 3 is not automatic; that ruling says when.

## Done-check

{{check}}
The lane can run it.
[ci_only] A check marked `proved at batch CI` is proved only there; the lane does not fail on it.

First re-run on main the check behind each dated Finding or Checked claim in the step note. Stop and report a failed claim. Report each: "Checked <Mon D> on main <commit>: <result>".
Before hand-in, run `~/.claude/bin/merge --lane-lint <pr>` (repos with `bin/ci-job`) and report its verdict; a red lane never hands in. Run `merge --lane-lint` from the main checkout, never from a session or agent isolated in a worktree: Claude Code's worktree check can refuse it there.
A coordinator-started lane hands in a draft PR to the batch runner. Only in claude-settings does it merge its own PR (decision `session-tiers`, merge path).

## Report cap

Time: `~/.claude/bin/now-central`. Cap {{cap}} lines: Done, Deviations, Input Needed, Next, "Port to other repos: yes or no, and why". Send questions to triage, and the green head and branch to the coordinator.

End archive-ready (operating model, Lane bullet).

Agent spawn brief head

A spawn brief's first line holds a marker alone.
Markers: `Guard or check: yes`, `Fix check`, `Round 2 of 3`, `Round 3 of 3` and `Audit:`.

None for product code or docs.
