# <step id>: <plain name of the step>

<Who runs it: a cloud lane session, or a lane session on a named local machine.> The coordinator
starts it with the tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`. Base: <branch and commit>.
The start prompt is `/effort medium` alone. This brief follows with `send_message` (`agent-model-cap`, the lane effort pin).
Never rebase onto main after review. Push record-branch edits to that branch only. Only triage publishes the page.
Run `git fetch origin +refs/heads/roadmap:refs/remotes/origin/roadmap` before the first Opus spawn and after triage writes a step grant. The guard reads only that local ref. A plain fetch does not write it in a shallow clone.

## Task

<What to build, and the outcome for the person the software serves.>

## Sources

<The files, records and rulings to read. Point at them. Never paste them in.>

## Fences

<What not to change, by intent, with each exception named.>

## Failure classes and proof

<The checks that prove the task done, and who reviews the diff.>

Batch-join check (repos with claude-settings' `bin/ci-job`): before the lane hands off, run
`~/.claude/bin/merge --lane-lint <pr>` once and report its verdict. It runs
`bin/ci-job checks --lint` at the PR head: the fast lint steps of the checks job, the STE lint
among them, and no full suite. A red lane does not hand off.

## Report

Cap <N> lines: Done, Deviations, Input Needed, Next. Add one line: "Port to other repos: yes or
no, and why". Send the green, reviewed head and branch to the coordinator. Do not merge.
