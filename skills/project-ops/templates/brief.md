Lane brief: <step-slug>. Topic: <topic-slug>. <Plain name of the step>.

<Who runs it: a cloud lane session, or a lane session on a named local machine.> The coordinator
starts it with the tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`. Base: <branch and commit>.
The coordinator also tags the lane `cs-topic:<topic slug>`, its one topic. The step slug is the step id.
The guard reads the Topic on the first line and refuses a brief whose Topic differs from that tag (rule `lane-one-topic`), so keep this line first.
The start names `model` (the lane row's) and `source_url` (the repo). The start prompt is `/effort medium` alone. This brief follows with `send_message` (`agent-model-cap`, the lane effort pin).
Never rebase onto main after review. Push record-branch edits to that branch only. Only triage publishes the page.
Run `git fetch origin +refs/heads/roadmap:refs/remotes/origin/roadmap` before the first Opus spawn and after triage writes a step grant. The guard reads only that local ref. A plain fetch does not write it in a shallow clone.

## Task

<What to build, and the outcome for the person the software serves.>

## Sources

<The files, records and rulings to read. Point at them. Never paste them in.>
For a test or merge change, name claude-settings decisions `test-practices` and `merge-practices`.

## Fences

<What not to change, by intent, with each exception named.>

## Failure classes and proof

<The checks that prove the task done, and who reviews the diff.>

Before it works, the lane re-runs on main the check behind each dated Finding or Checked claim in its
step note. If a claim no longer holds, it stops and reports.
Its report gives each re-run as "Checked <Mon D> on main <commit>: <result>", for triage to copy into the note.

Batch-join check (repos with claude-settings' `bin/ci-job`): before the lane hands off, run
`~/.claude/bin/merge --lane-lint <pr>` once and report its verdict. It runs
`bin/ci-job checks --lint` at the PR head: the fast lint steps of the checks job, the STE lint
among them, and no full suite. A red lane does not hand off.

A fix round is a fresh isolated spawn from the branch head (decision `lanes-start-in-tool-worktrees`: lanes start only in the tool's own worktrees).

## Report

Read each time you write from `~/.claude/bin/now-central`, never from memory.
Cap <N> lines: Done, Deviations, Input Needed, Next. Add one line: "Port to other repos: yes or
no, and why". Send the green, reviewed head and branch to the coordinator. Do not merge.
