# Classic-only readers read a ruleset as no protection

**What.** Three prose and audit readers look only at classic branch protection. On a repo whose `main` has a ruleset and no classic protection, that read finds nothing, so the reader can call the repo unprotected. They give false alarms only after the child-repo sweep applies a ruleset. All three must read the ruleset first before the sweep applies any ruleset.

**Where.** `skills/ci-hygiene/SKILL.md:282-283` (check 3, the classic protection read); `skills/compliance-check/probes.md:40` (the Git row, `branches/main/protection`); `actions/stamp/README.md:333` (`merge.requiredChecks`, item 3). The `pinned_required` docstring at `hooks/guard_merge.py:273` is wording only: the guard's batch read already goes through `protection_names` to `ruleset_names` (`merge/merge.py:1192-1194`, `:1697`).

**Decision.** `main-branch-protection` (owner ruling r moves `main` to a ruleset, and the merge tool reads the ruleset first).

**Retire.** Each of the three reads the ruleset first, as `protection_names` in `merge/merge.py` does, and says so in its text. The `hooks/guard_merge.py:273` docstring needs wording only. `test_ruleset_readers.py` is still to be written. It will check the three sites and fail while any of them reads classic protection alone, and pass once all three are rewritten.
