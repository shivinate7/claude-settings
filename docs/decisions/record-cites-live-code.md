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

Lane pick, 2026-11-08 04:16 CST, process-only, under the 04:03 reading: a dead cite has one home, STALE010 (a cite to a Python name missing at head). STALE009 (a report that never fails) covers only a code claim with no cite. A name the range removed stays STALE002 (a cite to a name the range removed from its file). A deleted or renamed path stays STALE001 (a line naming a path the range deleted or renamed). The 04:03 reading says a missing name "is red". The lane reads that as red on added lines only. So a PR is never red on work it did not do.

## The mistakes and the harm

- Pull request #1419 at commit 7156e9a3 said the ledger reads no CI state, but the merge tool reads main's latest CI run (merge/merge.py base_state). A reader who trusts the record misjudges what the tool does.
- #1553 merged a note citing lint/stale_cites.py `CODE_CLAIM` before #1539 added it. CI was green. A dead cite sends the reader to a name that is not there.

Claude writes both in normal work: it states what code does from memory, and it cites names from a branch that has not landed.

## How it works

- The cite uses the forms the stale-prose check already reads: "`file.py` `name`", "(file.py name)" and a test node id. A dotted name reads its first part.
- STALE009 reports, never fails: a sentence on a line a range adds in a decision record that states what code does, with no code cite (lint/stale_cites.py `CodeClaimReader`).
- STALE010 fails the PR: a line a range adds in governed Markdown cites a Python name, and the file is absent at head or the name is not bound there (lint/stale_cites.py `dead_name_cites`).
- STALE011 fails the PR: a line a range adds in governed Markdown cites a line anchor `file.py:N` or `file.py:N-M`, its sentence names a symbol the cite's file binds (a name is judged only when it holds an underscore or an inner capital or is a call, a dotted name by its last part, a file name offers none; the file binds it by a def or class at any depth or a module-level assignment, whole statement, never a local), and the name falls at no cite of that sentence: a name is placed when a def or class span of it, or a line holding it, falls within three lines of some cite of the sentence, and a cite fails only when none of its file's bound names holds there and one is placed at no cite (lint/stale_cites.py `anchor_name_cites`). `--tree` judges every line.
- Whether the claim is true stays with the reviewer: `agents/reviewer.md` reads each cited name against its claim.
- The module docstring of `lint/stale_cites.py` and `skills/fresh-prose/SKILL.md` state the cost. Both run inside the existing ste-lint step.

## Open

- Recall of STALE009 is unmeasured; its known misses are in the debt notes (`docs/debts/notes.md`).
- Dated by: a change to the cite forms under How it works, or STALE009 moving from a report to a finding.

Kind: build
Plan: docs/decisions/record-cites-live-code.md#how-it-works (all)
Home: lint/stale_cites.py
