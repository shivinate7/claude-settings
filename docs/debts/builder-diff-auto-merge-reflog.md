# Builder merge by strategy is not judged

**What.** A builder's merge that git commits with a strategy option is not judged. `git merge -X ours`, `git merge -X theirs` and `git merge -s ours` commit the merge with no `git commit` step. The HEAD reflog gets the subject `merge <branch>: Merge made by the '<strategy>' strategy.`. No reader matches that subject. So a builder that resolves a test conflict this way goes unjudged at commit, push and stop, and can drop one side's test cases. A `git pull` with those options, when it merges, writes a `pull` subject that no reader matches either. Claude could run such a merge in normal work. Harm: a builder drops one side's test cases, against owner ruling page item 437 a (2026-11-08 12:16 CST).

**Where.** `hooks/guard.py`. `ENTRY_OWN` (line 2012) matches `commit`, `commit (initial)`, `commit (amend)` and `commit (merge)`. `ENTRY_RESOLVED` (line 2014) matches `commit (cherry-pick)` and `revert`. `ENTRY_REBASE` matches rebase steps. No pattern matches the strategy merge subject. So `entry_kind` (line 2024) returns `''`, and `own_changes` judges only the `OWN` and `NOTED` kinds.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests.

**Retire.** The fix step is `step:builder-diff-auto-merge-reflog`. It judges such a merge as `own_changes` judges a `commit (merge)`. Closed when `hooks/test_guard.py` has a case where a builder's `git merge -X ours` drops a test case, the guard refuses it with `builder-diff`, and the case passes.
