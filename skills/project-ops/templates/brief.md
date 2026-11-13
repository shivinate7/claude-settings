Grant: <owner words>, <time>
Lane brief: {{slug}}. Topic: {{topic}}.

The coordinator starts the lane with the tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`, and tags it `cs-topic:<topic-slug>`. Base: <branch and commit>.
The test-author and the builder each get their own isolated worktree. They never share one worktree. A test commit lands on the lane branch before the builder starts. The builder's worktree then starts from that branch head. The builder never cherry-picks, amends or rewrites a test commit, and reports the test change it needs.
Each agent runs its role row in decision `agent-model-cap`. A product edit to `janitor/mutate_sweep.py`, `hooks/mutate_guard.py` or `hooks/mutate_shared.py` goes to a test-author run, never a builder.
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
The test-author writes the new cases red first, and the builder takes them green.
The diff gets review round 1 under ruling `r9` in roadmap/rulings. Round 3 is not automatic: `r9` says when it runs.

## Done-check

{{check}}

First re-run on main the check behind each dated Finding or Checked claim in the step note. If one no longer holds, stop and report. Report each re-run as "Checked <Mon D> on main <commit>: <result>".
Before hand-in, run `~/.claude/bin/merge --lane-lint <pr>` once (repos with `bin/ci-job`) and report its verdict; a red lane does not hand in. Run `merge --lane-lint` from the main checkout, never from a session or agent isolated in a worktree: Claude Code's worktree check can refuse it there.
Hand in a draft PR to the batch runner. Never merge.

## Report cap

Read the time from `~/.claude/bin/now-central`, never from memory. Cap {{cap}} lines: Done, Deviations, Input Needed, Next, "Port to other repos: yes or no, and why". Send each question to triage and go on. Send the green head and branch to the coordinator.

Agent spawn brief head
Put one marker on the first line of each spawn brief, at the line start:
Guard or check: yes
Fix check
Round 2 of 3
Round 3 of 3
Audit:
None for product code or docs.
