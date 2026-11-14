# An unmerged mockup branch was deleted

- **What.** An unmerged design branch was deleted, and its mockup is on no ref. Degen's `jd-deferred.html` (owner pick B, 2026-10-26 23:45 CDT) is cited by degen's `plan.md` and `native/Degen/JdDeferredPage.swift`. Product repos hold no `archive/*` branches (2026-11-02 note).
- **Where.** The branch delete. The code that deletes it is not located. The janitor sweep, `.gitignore` and the designer-scope guard are ruled out.
- **Decision.** `none`. No decision record fits. The rule `shared-trees-archive-then-delete` (archive an unmerged branch before a delete) governs it.
- **Retire.** The guard check on branch `design-branch-delete` refuses a remote delete of an unarchived design branch, one whose diff holds `docs/design` files that main lacks. Its record: decision `design-branch-delete-guard` on that branch.
