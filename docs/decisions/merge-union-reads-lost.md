---
id: pending
slug: merge-union-reads-lost
---

# A merge that unions entries, or renames or flips a registered case, loses none

## The ruling

Mistake: the builder merge check refused a correct merge. Both parents added entries to one statement that holds no test case, a case tuple in a function or a module-level table. The result kept every entry of both. The check read it as `lost` and as `body`, because the base version of the statement is in neither parent. Incident: lane receipt-close-express, PR #3264, 2026-11-17 19:49 CST. Harm: a correct merge was refused, and the lane stalled until a test-author took the merge.

This record narrows the lost-edit reading in `builders-cannot-edit-tests` (the merge route under Roles). It adds no new allowance for a case body.

- `merge_test_issue` in `hooks/guard.py` reads a statement as a union when the result, both parents and the base differ only in the entries of list, tuple, set and dict displays (`_is_union`). Any other difference is no union.
- A display is a union when the result holds each entry as often as the parent that holds it most, and no more often than both parents added it beyond the base (`_entry_union`). The result holds no entry neither parent holds.
- A union is not a dropped edit (`_edit_dropped`) and is not a `body` change.
- Still refused as `lost`: a result that drops any entry of either parent, a deliberate removal of a base entry that the other parent keeps, and a result that adds an entry neither parent had.
- A case body is read as before. It is no union.
- Open gap: a parent's deliberate deletion of a test case is not honoured (debt `merge-deliberate-case-removal-unhonoured`, deliberate removal unhonoured). This record does not touch it. A parent's rename of a registered call, row or helper is honoured below. A parent's rename of a `test_*` function is not (see the open gap below).

Cost: no process and no file. One more walk of the parsed statements per conflicted test path, inside the guard hook already running (unmeasured).

## A renamed registered call, row or helper, or one whose verdict flipped, is not lost

Mistake: the builder merge check read a case as lost though the result held it. Main had renamed a case function and its registered description and flipped its expected verdict (refused to asked). The lane's version kept the old names. The result took main's. The check matched a case by its full text, so the lane's old text was "gone". Incident: PR 3606 (lane glued-amp-on-any-filter), 2026-11-21 10:10 CST, section 34371 of the guard tests: 103 registered cases, all held, read as lost. Harm: a correct merge was refused with a false class. A reader who meets that false alarm learns to scroll past the true one.

- `merge_test_issue` in `hooks/guard.py` matches a case by its case key (`_case_key`): the statement with its function name and docstring dropped, the description of a call (its first argument, when it has three words or more) blanked, each verdict word (allow, ask, deny, refuse, lift, in any ending) masked, and a verdict keyword (`want="ask"`) dropped.
- A function that the result holds under another name pairs with the parent's function when their case keys are equal (`_def_renames`). A call that names it reads the new name.
- A case is lost only when the result holds fewer calls or statements of its case key than a parent does. The text match runs first. The case key runs only for a statement that the text match calls lost.
- A key that both parents changed from the base (`_edit_dropped`) is lost, even when the edits only rename a case or flip its verdict, since the result keeps one version at most. A result that drops a parent's edit stays lost, though the case keys match: a dropped rename or flip, a dropped edit of a table row, and a swapped identifier such as `PUSH_ALLOWED` for `PUSH_DENIED`. A name is not verdict-masked when an underscore or a digit joins it to other letters.
- A test function that the result holds under another name reads `renamed`, as before, by its case key.
- A statement a parent added is lost when the result holds fewer under its key (a def or class by its name, an assignment by its targets, any other statement by its text). A statement a parent edited is lost under the same count, unless the result holds its exact text under another def name: the def's name and docstring aside, verdict words unmasked, a renamed name read as its new name. A class or an assignment that the result renames is lost. A call a parent added or edited is lost when the result holds fewer calls of its exact text. A call the base holds is held by its case key (verdict masked, description blanked), and a base def that no parent edited is carried over by a rename on its case key.
- Open gap: a parent's rename of a `test_*` function still reads `lost` (`_def_renames` pairs only module statements that are not cases). Only a rename of a registered call, row or helper is honoured (note `merge-test-func-rename-lost`).
- Still refused as `lost`: a deleted registered call, row or function, including one whose twin differs only in verdict (the result holds fewer of the key than a parent). The case key adds nothing to `new` or `body`: a rename that the builder writes itself reads `new` or `body`.
- Open gap: two parents' different edits to one function under the same name read `lost` whichever version the result keeps, and when it combines both (`_edit_dropped`). Only identical edits, or edits that only add entries to a display both parents extended, pass (`_union_keys`). A result that renames a statement with its base text, and keeps the other parent's body edit, reads `body`, not `lost`. Note `merge-combined-edit-reads-body` (the same-name case, a false alarm) records the open gap.
- Open gap: a twin of the same case key can stand in for a deleted case when the result duplicates the twin. No honest merge writes that.

Reader: the class in the `builder-diff` reason, read by the builder and by the orchestrator that routes the merge to a test-author.

Cost: no process and no file. One `ast` deep copy of each statement that the text match calls lost, per conflicted test path, inside the guard hook already running (unmeasured).

Why: a union of both parents' entries keeps everything either parent wrote. The check exists to stop a lost test, and a union loses none.

Kind: process
Home: hooks/guard.py
