# A claim about code cites a live code name

## The question

How does a record's claim about what code does stay true, and how does a cite to code stay live?

## The ruling

Coordinator, 2026-11-07 15:06 CST, lane brief `record-claim-cites-code`. Quote:

> "a record sentence that says what code does or does not do cites the code symbol (`module.symbol`). The skill's check then confirms that the symbol exists. Whether the sentence is true stays with the reviewer"

Coordinator, 2026-11-07 15:08 CST: "one grammar and report-only are fine". The cite uses the forms the stale-prose check already reads: "`file.py` `name`", "(file.py name)" and a test node id.

Coordinator, 2026-11-08 04:03 CST, item 386 (a cite that runs ahead of its code). Quote:

> "lane lint runs stale_cites on the PR's own tree (base plus PR), so a cite to a code name missing there is red"

Lane pick, 2026-11-08 04:16 CST, under that ruling: a dead cite has one home, STALE010. STALE009 reports only a code claim with no cite. A name the range removed stays STALE002. A deleted or renamed path stays STALE001.

## The mistakes and the harm

- Decision `pr-ledger` (#1419, commit 7156e9a3) said the ledger reads no CI state, but the merge tool reads main's latest CI run (merge/merge.py run_state). A reader who trusts the record misjudges what the tool does.
- #1553 merged a note citing lint/stale_cites.py `CODE_CLAIM` before #1539 added it. CI was green. A dead cite sends the reader to a name that is not there.

Claude writes both in normal work: it states what code does from memory, and it cites names from a branch that has not landed.

## How it works

- STALE009 reports, never fails: a sentence on a line a range adds in a decision record that states what code does, with no code cite (lint/stale_cites.py `CodeClaimReader`).
- STALE010 fails the PR: a line a range adds in governed Markdown cites a Python name, and the file is absent at head or the name is not bound there (lint/stale_cites.py `dead_name_cites`).
- Whether the claim is true stays with the reviewer: `agents/reviewer.md` reads each cited name against its claim.
- The module docstring of `lint/stale_cites.py` and `skills/fresh-prose/SKILL.md` state the cost. Both run inside the existing ste-lint step.

## Open

- Recall of STALE009 is unmeasured; its known misses are in debt `stale010-class-level-names` and the notes.
- Dated by: a change to the cite forms the check reads, or STALE009 moving from a report to a finding.

Kind: build
Plan: docs/decisions/record-cites-live-code.md#how-it-works (all)
Home: lint/stale_cites.py
