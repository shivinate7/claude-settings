# A claim about code cites a live code name

## The question

How does a record's claim about what code does stay true, and how does a cite to code stay live?

## The ruling

Owner ruling, waiting-page item 386, titled "Make merges keep pace with reviews: which parts do you want?", answered 2026-11-08T04:25:43Z, which is 2026-11-07 22:25 CST. Its choice was a, b and c. Option b, "Findings ride in their lane (recommended)", reads: "A lane's findings join its next commit, or one follow-up PR per topic, not one new lane each." Option b is why the dead-cite check, STALE010, was built in this lane. The item does not rule on cite forms.

Coordinator readings:

- 2026-11-07 15:06 CST, coordinator reading, process-only (lane brief `record-claim-cites-code`): "My judgement: fold it into the fresh-prose skill (skills/fresh-prose) and its existing check, not a new lint. The rule: a record sentence that says what code does or does not do cites the code symbol (`module.symbol`). The skill's check then confirms that the symbol exists. Whether the sentence is true stays with the reviewer"
- 2026-11-07 15:08 CST, coordinator reading, process-only: "one grammar and report-only are fine."
- 2026-11-08 04:03 CST, coordinator reading, process-only (item 386; #1539 is the PR that adds CODE_CLAIM): "Your lane owns stale_cites (CODE_CLAIM), so the guard rides with you (item 386), as a follow-up from #1539's head with `Merge after: #1539`: lane lint runs stale_cites on the PR's own tree (base plus PR), so a cite to a code name missing there is red."
- 2026-11-08 07:43 CST, coordinator reading, process-only: "go ahead with record-cites-live-code."
- 2026-11-08 08:43 CST, coordinator reading, process-only: "yes, fix debt stale010-no-top-folder now. Other repos will hit it when their ste-lint pin moves, so Claude is likely to hit it in normal work. Under item 386 it rides in your lane: open a follow-up PR now with `Merge after: #1893`. Reuse STALE003's top-folder test, and do not copy it. Red first: the src-layout cite and the `(django/db/models.py Model)` cite. It is a check change, so it runs rounds 1-3 from round 1. Point the debt's Fix line at its step."
- 2026-11-08 10:23 CST, coordinator reading, process-only: pick (b), a cite into a top folder tracked in history is still checked, at one git log start.

Lane pick, 2026-11-08 04:16 CST, process-only, under the 04:03 reading: a dead cite has one home, STALE010 (a cite into a tracked top folder to a Python name missing at head). STALE009 (a report that never fails) covers only a code claim with no cite. A name the range removed stays STALE002 (a cite to a name the range removed from its file). A deleted or renamed path stays STALE001 (a line naming a path the range deleted or renamed). The 04:03 reading says a missing name "is red". The lane reads that as red on added lines only. So a PR is never red on work it did not do.

Orchestrator ruling, 2026-11-13 11:47 CST, process-only (build brief of the rebuild of lane `record-claim-cites-code`): a failed `git log` of the history read is one `stale-cites: unknown` line with the exit 0, and the folder stays silent. It joins no exit-2 read of decision `stale-cites-at-merge`.

## The mistakes and the harm

- Pull request #1419 at commit 7156e9a3 said the ledger reads no CI state, but the merge tool reads main's latest CI run (merge/merge.py base_state). A reader who trusts the record misjudges what the tool does.
- #1553 merged a note citing lint/stale_cites.py `CODE_CLAIM` before #1539 added it. CI was green. A dead cite sends the reader to a name that is not there.

Claude writes both in normal work: it states what code does from memory, and it cites names from a branch that has not landed.

## How it works

- The cite uses the forms the stale-prose check already reads: "`file.py` `name`", "(file.py name)" and a test node id.
- STALE009 reports, never fails: a sentence on a line a range adds in a decision record that states what code does, with no code cite (lint/stale_cites.py `CodeClaimReader`).
- STALE010 fails the PR: an added line in governed Markdown cites a Python name in a tracked top folder, or in a top folder that history tracked and head no longer has. The file is absent at head, or the name is not bound there (lint/stale_cites.py `dead_name_cites`, `history_tops`). The top-folder test is the one STALE003 applies (lint/stale_cites.py `in_tracked_top`).
- A top folder neither at head nor in history, such as `django/`, stays silent. History is one `git log` of deleted paths, started once per range when an added cite names a folder absent at head. A failed log is unknown, and the folder stays silent.
- Whether the claim is true stays with the reviewer: `agents/reviewer.md` reads each cited name against its claim.
- The module docstring of `lint/stale_cites.py` and `skills/fresh-prose/SKILL.md` state the cost. Both run inside the existing ste-lint step.

## Open

- Recall of STALE009 is unmeasured; its known misses are in the debt notes (`docs/debts/notes.md`).
- Dated by: a change to the cite forms under How it works, or STALE009 moving from a report to a finding.

Kind: build
Plan: docs/decisions/record-cites-live-code.md#how-it-works (all)
Home: lint/stale_cites.py
