# <step id>: <plain name of the step>

<Who runs it: a cloud build thread or a local session.> Base: <branch and commit>. Never rebase
onto main after review. Push record-branch edits to that branch only. Only triage publishes the page.

## Task

<What to build, and the outcome for the person the software serves.>

## Sources

<The files, records and rulings to read. Point at them. Never paste them in.>

## Fences

<What not to change, by intent, with each exception named.>

## Failure classes and proof

<The checks that prove the task done, and who reviews the diff.>

Batch-join check (repos with claude-settings' `bin/ci-job`): before the lane joins a batch, run
`bin/ci-job checks --lint --base origin/main` and report its verdict. It runs the fast lint steps of
the checks job and no full suite. Also run `bin/ste-changed origin/main`: the mode skips a `uses:` step,
and the STE lint is one.

## Report

Cap <N> lines: Done, Deviations, Input Needed, Next. Add one line: "Port to other repos: yes or
no, and why". Send the green, reviewed head and branch to the build advisor. Do not merge.
