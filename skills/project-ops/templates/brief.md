Grant: <owner words>, <time>
Lane brief: <step-slug>. Topic: <topic-slug>. <Plain name of the step>.

The lane treats the Grant line as the owner's grant. It checks the grant against the coordinator's chat only when the act cannot be undone.

<Who runs it: a cloud lane, or a lane on a named local machine.> The coordinator
starts it with the tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`. Base: <branch and commit>.
The coordinator also tags the lane `cs-topic:<topic slug>`, its one topic. The step slug is the step id.
Rule `lane-one-topic` reads the Topic on the first non-blank line of a brief sent by `send_message`. It reads a lane start prompt the same way, after its Grant line. So such a brief opens with the `Lane brief:` line.
The start names `model` (the lane row's), `source_url` (the repo) and effort `medium`. The start prompt is this whole brief, and it opens with the Grant line (`agent-model-cap`, the lane effort pin).
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
Run `merge --lane-lint` from the main checkout, never from a session or agent isolated in a worktree: Claude Code's worktree check can refuse it there.

A fix round is a fresh isolated spawn from the branch head (decision `lanes-start-in-tool-worktrees`: lanes start only in the tool's own worktrees).

The test-author and the builder each get their own isolated worktree (decision `lanes-start-in-tool-worktrees`; rule `parallelism-each-own-checkout`: each agent in its own checkout). They never share one worktree. A test commit lands on the lane branch before the builder starts. The builder's worktree then starts from that branch head. The builder never cherry-picks, amends or rewrites a test commit. An amend, or a commit after `cherry-pick -n` or `merge --squash`, is the builder's own commit holding test files, so the builder-diff guard refuses the builder's next commit. The builder reports the test change it needs, and the lane gives that change to a test-author. The guard is right (decision `builders-cannot-edit-tests`: builders cannot edit tests).

On an iPhone app, the builder runs its own app build. Another session's running build does not block it: the one-build rule counts only builds of the builder's own session (skill `ios-apps`, "Sharing the Mac").

## Report

Read each time you write from `~/.claude/bin/now-central`, never from memory.
Cap <N> lines: Done, Deviations, Input Needed, Next. Add one line: "Port to other repos: yes or
no, and why". Send the green, reviewed head and branch to the coordinator. Do not merge.
