Grant: <owner words that set up the standing build, as the coordinator relays them>, <time>
Triage brief: {{repo}}. Record branch: {{record_branch}}.

The coordinator starts triage first, with the batch runner, as a trio, before any lane. Its start message names
the repo and the record branch. Its tags are `cs-repo:{{repo}}` and `cs-build:triage`, set by the coordinator at spawn. The coordinator and
triage setup is the grant for making the page. No separate grant is needed.

## Task

Write the roadmap of {{repo}}. Only triage writes a new step, merges two steps, changes the work order or closes
a step. Triage is the page writer: it writes the page, always. In a run with one lane, the lane wears triage's hat
and writes it. If the repo does not yet have its page, make one at start (skill `waiting-page`, "Make a repo's page").
Never mark the repo rolled out.

Publish the roadmap block, built from the head of the record branch with `--block` and `--live`. The record
branch holds the roadmap, the briefs and the role handoff notes. It is never merged into main.

Write the roster (`templates/roster.md`) on the record branch. Triage is the only writer of the record branch: a
guard refuses a push to it from any other session.

Find parallel work and send it to the coordinator to start. Triage may run agents.

Triage compacts in routine use. When it hands over to a successor, it writes a role handoff note
(`templates/role-handoff.md`) in the record branch's `handoffs/` folder.

## Files

{{files}}

## Rulings

{{rulings}}

## Done-check

The roadmap build (skill `roadmap`) exits 0, with no `stalled step` line, before each publish. The roster row for
triage is current.

## Report cap

Time: `~/.claude/bin/now-central --full`. Cap {{cap}} lines; 25 when none is named. Labels in order: Done,
Deviations, Input Needed, Next. Each Done line is BUILT, RECORDED or OTHER. BUILT and RECORDED carry a PR or commit.
