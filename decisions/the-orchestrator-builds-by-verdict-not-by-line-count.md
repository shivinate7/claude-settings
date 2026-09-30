# A session builds by the request and the verdict, never by line count

Supersedes README Decision 13, "the orchestrator and product code: judge the act,
not the file". That entry replaced a file test with a size test. This entry
replaces the size test with a request test and a verdict test.

## The rule now

The session picks solo or orchestrate from the owner's request. It says its pick
in one line before it starts.

- **Solo.** The request is a short list of edits, with nothing to run in parallel.
  The session builds them itself. A fresh reviewer reads the diff before merge
  only when the diff touches a rule's behaviour, a gate's verdict, or program
  logic. Text, style, and content edits merge on passing checks alone.
- **Switch.** If a solo job grows, or parts could run in parallel, the session
  switches to orchestrate and says so in one line.
- **Orchestrate.** Every other job. The session plans, briefs, verifies, and
  reports. It builds only when the change cannot move a verdict and one bounded
  command proves it. A change that touches a rule's behaviour, a gate's verdict,
  or product code a reviewer must see goes to a lane, at any size. A ceiling of
  about 40 lines stays, against reading cost alone.

## What the rule protects

Edits that no second reader sees. The reviewer now runs on rule, gate, and logic
diffs, where a wrong edit changes what the software does. A wrong word in a doc
changes nothing that a check would miss and a reviewer would catch.

It also protects the context the session already holds. A builder reloads the
repo for work the session can do at once.

## Evidence

A session was asked for six one-word text swaps. The old rule made it an
orchestrator, so it sent each swap to a builder. Each builder reloaded the repo,
while the session already held it. The six edits moved no verdict. The lanes cost
more than the edits, and no reviewer was needed.

The size test also failed the other way. One flipped comparison in the liveness
read was one line. It would have made every session read as dead. A line count
would let it pass unreviewed. The verdict test sends it to a reviewer.

## The mechanism

`lint/rule_mechanisms.json` records the four solo rules and
`roles-orchestrator-never-builds` as unmechanized. A hook can count lines. It
cannot tell a short edit list from a job that could fan out, or a text diff from
a logic diff.

`hooks/decision_watch.py`, a Stop command hook, judges the act and escalates to a
model for the residual judgment. See
`decisions/stop-guardrail-became-a-command-hook.md`. The check stays a read of the
act.
