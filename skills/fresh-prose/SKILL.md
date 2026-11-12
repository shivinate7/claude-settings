---
name: fresh-prose
description: Use when a session writes or updates a README, docs, CLAUDE.md, agent files, or decision records, or when the user says "stale docs" or "fresh-prose". Makes prose hard to go stale, by binding each claim to a check.
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
5. **Check it.** CI fails if a claimed path, link, or reference does not resolve. For links,
   adopt claude-settings' `actions/readme-links`. A cite to a record in a wrong wrapper, such
   as ``D`slug` ``, is a near-miss. The stamp rewrite never matches it, so the cite stays dead
   text until someone writes the cite form. For cites, adopt the near-miss check of
   claude-settings' `actions/stamp`. It names the cite form to write.

Use the tools the repo already has: its language, its test runner, its CI. Add a dependency
only if a small script cannot do the job, and name each dependency you add, with the reason.

## Prose types and their rung

| Prose | Claims that rot | Rung that fits |
| --- | --- | --- |
| README | see `readme.md` in this skill | see `readme.md` |
| CLAUDE.md, agent files | "the guard refuses X", file paths | Check it: link each rule to a test that runs and goes red. `lint/rule_audit.py` checks only that the test exists and is collected. The red runs are in `lint/test_rule_audit.py` and `hooks/mutate_guard.py` |
| Rule text that a hook injects into a session | the copy drifts from the rule it copies | Check it: name the source of the copy, and add a test that fails when the printed text and the source differ |
| docs, guides | commands, flags, config keys | Generate from `--help` or the schema, or run the commands in CI |
| Decision records | "we chose X because Y was true" | A trigger, not a test: name the fact that would date the record |
| Code comments | "this is called from A", "the cap is 10" | Delete it, or move the fact next to the code it describes |
| PR bodies, reports | anything | Skip them. They are snapshots. Nobody rereads them |

## Reasons

A reason, "we chose X because Y", cannot be checked by a machine. Write the fact Y next to the
reason. A check or a person then compares that fact with the repo. A reason with no named fact
is not yet on the ladder.

## Rewrite, never annotate

When a fact changes, rewrite the claim in place and add no "was X, now Y" line
(`speak-rewrite-superseded-in-place`). A decision record whose ruling changes is rewritten in
its own record (`git-one-record-per-question`).
The ste-lint CI step refuses a pull request that leaves stale prose (`lint/stale_cites.py`).
STALE001 fires on a tracked Markdown line that names a file the same pull request deleted or renamed.
STALE002 fires on a line that cites a Python file and a name the pull request removed from that file.

## Record rules

Never allocate a numbered record on a branch. Write a slug of 32 characters or fewer. Claim the number at merge. Name a lane by its branch slug, never by a session number.<!-- rule:git-slug-then-claim-number --> Ids, not paths. A path breaks when its file moves.<!-- rule:git-cite-by-id --> Give each record its own file, one folder per kind.<!-- rule:git-record-own-file-per-kind --> One record per question. When its ruling changes, rewrite the record in place. Open a record only for a new question.<!-- rule:git-one-record-per-question -->

## Published numbers

If this repo lints markdown, give every published number and path a checked reader.<!-- rule:verification-checked-reader-for-numbers -->

## Proof

Proof (`verification-trust-guard-after-red`): break the target on a scratch copy, watch the
guard fail, restore the target. Give each guard's verdict in one line.

## README

Writing or updating a README: read `readme.md` in this skill folder before you start.
