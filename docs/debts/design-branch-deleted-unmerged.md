# An unmerged mockup branch was deleted

- **What.** An unmerged design branch was deleted, and its mockup is on no ref. Degen's `docs/design/jd-deferred.html` (owner pick B, 2026-10-26 23:45 CDT) is cited by degen's `docs/specs/plan.md` and `native/Degen/JdDeferredPage.swift`. Product repos hold no `archive/*` branches (2026-11-02 note).
- **Where.** The branch delete. The code that deletes it is not located. The janitor sweep, `.gitignore` and the designer-scope guard are ruled out.
- **Decision.** `waiting-data-in-repo` (git is each artifact's home).
- **Retire.** Refuse a branch delete whose diff holds `docs/design` files that main lacks, unless the branch is archived first (rule `shared-trees-archive-then-delete`). Check: none yet.
