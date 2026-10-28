# c156-outside-write-guard

- Status: green and reviewed. Draft PR #749 (other-checkout guard rule), head dd1ce4fd.
- Built: guard rule `other-checkout` refuses any session's write into another checkout of the same clone; allows paths in no checkout; owner override lifts it.
- Tests: new cases red first on main, green now. Full guard suite green except the load-brake probe case, which is red on main too. `ci-job gates --lint` PASS. Silent-undo check clean.
- Review: round 1 opus (5 fixes made), round 2 sonnet merge-ready. 3 low findings are in docs/debts/notes.md (other-checkout-*).
- Not done: the Banchi part (another repo; needs the owner's plan check).
- c161 (load-brake probe test) can start after this lane merges.
