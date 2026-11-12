# Classic-only readers read a ruleset as no protection

**What.** Four readers look only at classic branch protection. On a repo whose `main` has a ruleset and no classic protection, that read finds nothing, so the reader can call the repo unprotected. All four must read the ruleset first before the child-repo sweep applies any ruleset.

**Where.** `skills/ci-hygiene/SKILL.md:282-283` (check 3, the classic protection read); `skills/compliance-check/probes.md:40` (the Git row, `branches/main/protection`); `actions/stamp/README.md:333` (`merge.requiredChecks`, item 3); `hooks/guard_merge.py:273` (the `pinned_required` docstring, the batch read).

**Decision.** `main-branch-protection` (owner ruling r moves `main` to a ruleset, and the merge tool reads the ruleset first).

**Retire.** Each of the four reads the ruleset first, as `protection_names` in `merge/merge.py` does, and says so in its text. `test_ruleset_readers.py` checks the four sites and fails while any of them reads classic protection alone. It is red now, and green once all four are rewritten.
