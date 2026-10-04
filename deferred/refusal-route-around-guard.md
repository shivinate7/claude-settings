# No guard stops an agent that routes around a refusal

**What waits.** A forced guard for this case. On 2026-10-03 in q_max, a test-author got an Edit
refusal, then wrote the same file with Bash and Python. No hook sees a write made that way. The
owner ruled prose only for now: `agents/builder.md` and `agents/test-author.md` say a refusal is
final. Decision builders-cannot-edit-tests records the ruling.

**Why it waits.** The owner chose prose first. One evasion is measured, and the reviewer caught
it.

**What keeps it from being lost.** This file.

**Trigger.** The owner asks for a forced guard, or a second route-around is measured. Two
options exist. Fix the base bug that decision builders-cannot-edit-tests names, so the diff
check blocks at stop and commit for any route. Or deny a shell command that names a path the
same agent was refused. The first judges the result, as that decision requires. The second
judges commands, which that decision rejected.
