# A decision's claims about a tool are not compared with the tool

- **What.** A decision can say what `merge/merge.py` does ("enforces", "refuses", "prints") with no check that runs the named function. Three such claims in the train decisions were false at review and caught only by reviewers: the freeze enforcement, the 70% job warning, and the malformed-block refusal.
- **Where.** `docs/decisions/batch-freeze-lane-set.md` and `docs/decisions/session-tiers.md`; no guard reads a decision's tool claims.
- **Decision.** `batch-freeze-lane-set` (a batch's lane set freezes when its build starts).
- **Retire.** A check runs each cited function on a probe input and compares the verdict with the claim. `merge/test_decision_claims.py` shows it red on a false claim and green on a true one.
