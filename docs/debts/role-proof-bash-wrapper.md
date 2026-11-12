# A merge --role call inside a bash -c wrapper passes the role proof

**What.** `role_proof_hit` reads the segments of a command and does not walk a `bash -c`, `sh -c` or `eval` wrapper, so a `merge --role` call inside one passes the role proof. Review 1 of PR #2815 (this branch's pull request) ran a probe that wrapped the batch-runner role call in `bash -c`, and it returned allow. This is pre-existing on main. The confirm check walks the wrappers (`_unproved_confirm`), so the gap is in the role proof only.

**Where.** `hooks/guard_merge.py`, `role_proof_hit`, called from step 6a of `hooks/guard.py` (rule `merge-role-proof`). The wrapper reader to reuse is `inner_commands`, which `_unproved_confirm` already calls.

**Decision.** `session-tiers`, its Proof sub-bullet (guard rule `merge-role-proof`, whose scope this gap breaks).

**Retire.** Add a case to the merge section of `tests/guard/s13406-merge.py`, which `hooks/test_guard.py` runs. The case is a `merge --role batch-runner` call inside `bash -c`, from a lane record that proves no role, and it expects a refusal. It is red while the wrapper passes.
