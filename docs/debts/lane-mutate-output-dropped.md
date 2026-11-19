# Lane lint drops the mutation test's output

**What.** `mutate_run_check` in the merge tool runs each mutation shard and keeps only the counts it parses from the output. A FAIL says "N mutants survived" or "unknown N", and never names the mutant or the "ERROR stale mutation" line. Mistake: Claude gets a FAIL and must find the mutant. Harm: Claude re-runs the shard for 11 to 16 minutes to read it. Reported 2026-11-09 (lane mutate-harness-change-timed-run); read again on main.

**Where.** `merge/merge.py`, `mutate_run_check` (its inner `run_one`), and `report_verdict` in `hooks/mutate_shared.py`.

**Decision.** `none`.

**Retire.** The FAIL names each failing mutant, and a timeout reads apart from a survivor. A case in `merge/test_merge.py` feeds a failing report and expects the mutant name in the lane-lint failure.
