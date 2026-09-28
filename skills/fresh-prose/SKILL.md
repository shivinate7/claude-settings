---
name: fresh-prose
description: Use when a session writes or updates a README, docs, CLAUDE.md, agent files, decision records, or comments that state facts about the code, or when the user says "stale docs" or "fresh-prose". Makes prose hard to go stale, by binding each claim to a check.
---

Every claim in prose can go stale. Give each claim a checked reader, so a stale claim gets
caught, not read past.

## The ladder

For each claim, take the first rung that holds.

1. **Delete it.** A claim nobody needs cannot go stale.
2. **Link to the source**, instead of stating the claim.
3. **Generate it.** Mark the block. One script regenerates every marked block from its
   source. CI runs the script and fails if the file changes.
4. **Run it.** CI runs the command in a clean checkout. A command that cannot run, for
   example a deploy, gets a short note that says why.
5. **Check it.** CI fails if a claimed path, link, or reference does not resolve.

Use the tools the repo already has: its language, its test runner, its CI. Add a dependency
only if a small script cannot do the job, and name each dependency you add, with the reason.

## Prose types and their rung

| Prose | Claims that rot | Rung that fits |
| --- | --- | --- |
| README | see `readme.md` in this skill | see `readme.md` |
| CLAUDE.md, agent files | "the guard blocks X", file paths | Check it: link each rule to what enforces it |
| docs, guides | commands, flags, config keys | Generate from `--help` or the schema, or run the commands in CI |
| Decision records | "we chose X because Y was true" | A trigger, not a test: name the fact that would date the record |
| Code comments | "this is called from A", "the cap is 10" | Delete it, or move the fact next to the code it describes |
| PR bodies, reports | anything | Skip them. They are snapshots. Nobody rereads them |

## Reasons

A reason, "we chose X because Y", cannot be checked by a machine. Write the fact Y next to the
reason. A check or a person then compares that fact with the repo. A reason with no named fact
is not yet on the ladder.

## Proof

Trust a guard only once it goes red on the defect it guards. To prove a guard, break its
target on a scratch copy, watch the guard fail, then restore the target. Give the verdict of
each guard in one line. A guard you did not see go red is not proven.

## README

Writing or updating a README: read `readme.md` in this skill folder before you start.
