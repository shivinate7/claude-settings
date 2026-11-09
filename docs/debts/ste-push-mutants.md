# No mutant covers the ste-push rule

**What.** No mutant in `hooks/mutate_guard.py` lands in `hooks/guard_ste.py` or in the ste-push block of `hooks/guard_merge.py`, and neither mutation file names `hooks/test_guard_ste_push.py`. The mutation gate reaches the rule only through one case in `hooks/test_guard.py`, so a change that weakens a ste-push verdict can pass CI. Step `ste-push-mutants` (mutants for the ste-push rule) fixes it.

**Where.** `hooks/mutate_guard.py`, `hooks/mutate_shared.py`, `hooks/guard_ste.py`, `ste_push_hit` in `hooks/guard_merge.py`.

**Decision.** `ste-lint-at-push` (the STE lint runs once at push).

**Retire.** Mutants on the ste-push verdicts (FAIL refuses, unknown allows, the chain refusal, the skips), each killed by `hooks/test_guard_ste_push.py`. The test file `hooks/test_mutate_ste_push.py` shows each mutant killed.
