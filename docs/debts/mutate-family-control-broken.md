# The mutate_guard --family clean-layout control is red for every family

**What.** With `--family`, the clean-layout control reads red for any family. A red control reads its mutants UNKNOWN, never killed (`hooks/test_mutate_shared.py`), so the mutants of that family read UNKNOWN. Builders reported it on PR #2774 (head d08e55b9a8d599665111ee33841ec61323506895) and on PR #2750 (head 89fec26ec59012994de9d2011d9428a28835c83f). Open on PR #2774 and PR #2750 until merge.

**Where.** `hooks/mutate_guard.py`, the `--family` path and `run_controls` (~4207 on main). The `--family` flag is on the PR heads, not on main.

**Decision.** `mutation-report-scores-suites`, the mutation report scores suites with mutants.

**Retire.** Closed when a case in `hooks/test_mutate_shared.py` runs `--family` on a clean layout, expects its control green, and expects each mutant killed. Test file: `hooks/test_mutate_shared.py`.
