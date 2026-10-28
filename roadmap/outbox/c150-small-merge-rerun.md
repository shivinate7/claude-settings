# c150-small-merge-rerun

- c150 status: try 3 pushed at 92aa1e43 (branch c150-small-merge-rerun). Review rounds 1 and 2 found blocking holes, both fixed. Round 3 (final, with net-value test) running. Resume: if no round-3 report, send a fresh reviewer the round-2 findings and the decision record merge-needs-current-base.
- Cost: a records-only main move costs about 13 min of local checks at merge (lints about 4 min, hit suites about 9 min, merge/test_merge.py alone about 8 min because it reads the real tree), against a 50-60 min CI re-run.
- Finding, no step yet: in a cloud container, hooks/test_guard.py "load-brake: probe control" (counted 2 children, want 1) and hooks/test_handoff_wave2.py (2 checks that need a file the run cannot delete) fail on main e0f9e2d too. Not caused by c150. In such a container the merge tool refuses a records-only move because test_handoff_wave2 is a hit suite.
