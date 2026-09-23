# The orchestrator builds by verdict, never by line count

Supersedes README Decision 13, "the orchestrator and product code: judge the act,
not the file". That entry replaced a file test with a size test. This entry
replaces the size test with a verdict test.

## What the old rule said

`CLAUDE.md`, the Roles paragraph: "never builds with one exception: the fix is
small (under 10 lines) and is named in the report."

## What the rule protects

Two things, and neither one tracks line count.

A builder's work gets a reviewer. The orchestrator's own work gets nobody. That
is the real exposure, and it is a property of the change, not of its size.

Building also spends the context this session needs to steer with, and it
serialises work that could fan out.

## Measured, 2026-09-22, in one session

The size test misfired three times in one direction. It would have waved through
the one change that mattered in the other.

| Change | Size | What the size test said | What the change actually was |
|---|---|---|---|
| The `SessionEnd` disarm | 11 deleted lines of JSON | borderline deviation | the most consequential act of two days, because it disarmed a machine-wide reaper |
| The disarm record and its session-start notice | about 25 lines | send it to a lane | the record names that notice as its mechanism, so the two are one act |
| The wrong-cause print in `hooks/mutate_guard.py` | 16 lines | deviation | moves no verdict, and every later step depended on the read it adds |
| One flipped comparison in the liveness read | 1 line | allowed, unreviewed | would make every session read as dead again |

The first three were named in a report as deviations. The fourth is the defect
this repository spent two days fixing.

## The rule now

The orchestrator builds when both of these hold:

1. The change cannot move a verdict. It adds no rule. It changes no allow or
   deny, no gate's pass or fail, and no promise a record makes. Diagnostics,
   prints, a skip that names its reason, records, docs, briefs and
   continuous-integration wiring sit inside this line.
2. One bounded command proves it, and the report names the change and that
   command's verdict.

The orchestrator briefs a lane when the change touches a rule's behaviour, a
gate's verdict, or product code a reviewer must see. Size does not matter
there. It also briefs a lane when the work could run beside other work.

A ceiling of about 40 lines stays, against reading cost alone. It is a circuit
breaker, never a safety argument.

## The mechanism

`lint/rule_mechanisms.json` records this rule as unmechanized, and its stated
reason names the ten-line exception directly.

It stays unmechanized on purpose. A hook can count lines. It cannot tell
orchestration from building. The only file-based version is the test Decision 13
already threw out, for misfiring on a decision entry.

The `Stop` guardrail in `settings.json` read the turn's transcript and judged
the act. It caught this rule's own breach on 2026-09-22 and asked for the
owner's word. That was this rule's check. The fix is the rule it judges
against, never a new hook.

`decisions/stop-guardrail-became-a-command-hook.md` records what replaced it
on 2026-09-22. Read that entry for the new mechanism.

This rule's own check is still a human read of the act. A command hook passes
through no permission check at all. It cannot go silent for that reason.

So read an UNKNOWN systemMessage from the new hook as a cue to look yourself.
A run of them means that the hook itself is failing. It never means that nothing
protected changed.
