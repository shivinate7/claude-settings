---
id: pending
slug: merge-union-reads-lost
---

# A merge that unions both parents' entries of one statement is not lost

## The ruling

Mistake: the builder merge check refused a correct merge. Both parents added entries to one statement that holds no test case, a case tuple in a function or a module-level table. The result kept every entry of both. The check read it as `lost` and as `body`, because the base version of the statement is in neither parent. Incident: lane receipt-close-express, PR #3264, 2026-11-17 19:49 CST. Harm: a correct merge was refused, and the lane stalled until a test-author took the merge.

This record narrows the lost-edit reading in `builders-cannot-edit-tests` (the merge route under Roles). It adds no new allowance for a case body.

- `merge_test_issue` in `hooks/guard.py` reads a statement as a union when the result, both parents and the base differ only in the entries of list, tuple, set and dict displays (`_is_union`). Any other difference is no union.
- A display is a union when the result holds each entry as often as the parent that holds it most, and no more often than both parents added it beyond the base (`_entry_union`). The result holds no entry neither parent holds.
- A union is not a dropped edit (`_edit_dropped`) and is not a `body` change.
- Still refused as `lost`: a result that drops any entry of either parent, a deliberate removal of a base entry that the other parent keeps, and a result that adds an entry neither parent had.
- A case body is read as before. It is no union.
- Open gap: a parent's deliberate deletion or rename of a test case is not honoured (debt `merge-deliberate-case-removal-unhonoured`, deliberate removal unhonoured). This record does not touch it.

Cost: no process and no file. One more walk of the parsed statements per conflicted test path, inside the guard hook already running (unmeasured).

Why: a union of both parents' entries keeps everything either parent wrote. The check exists to stop a lost test, and a union loses none.

Kind: process
Home: hooks/guard.py
