# The infinitive and lead-word exemptions of the pass-claim check have no test

**What.** Review round 3 ran 11 mutants of `hooks/pass_claim.py`. Four survive every case of `PassClaimCitesVerdictTests`: dropping `_infinitive` (both forms), emptying `LINKING_VERBS`, and emptying `LEAD_CONNECTORS`. The behaviour is ruled: "for the tests to pass" and "Please confirm the tests pass" are no claim.

**Where.** `hooks/pass_claim.py` (`_infinitive`, `LINKING_VERBS`, `LEAD_CONNECTORS`); `lint/test_report_guard.py` class `PassClaimCitesVerdictTests`.

**Decision.** `pass-claim-cites-verdict` (a pass claim cites its verdict line). Found in review round 3 of PR 2851.

**Retire.** A test-author adds one red-then-green pair per surviving mutant, so each mutant turns a case red. `lint/test_report_guard.py` shows it closed.
