# The fed-write carry has no mutation rows, so its cases are not proven to pin it

**What.** The fed-write carry, the depth and maxdepth reader in `hooks/guard_frozen.py`, has no mutation row. So the mutation report cannot say whether cases s20369, s22868, s18211 and s21922 catch its removal. Mutation rows live in `hooks/mutate_guard.py`, which a builder may not edit, so a test-author adds them. Found in PR #2774, head d08e55b9a8d599665111ee33841ec61323506895; open on PR #2774 until merge.

**Where.** `hooks/guard_frozen.py`, the depth and maxdepth reader. Rows go in `hooks/mutate_guard.py`.

**Decision.** `mutation-report-scores-suites`, the mutation report scores suites with mutants.

**Retire.** Closed when the test-author adds a row for the carry and its mutant is killed by cases s20369, s22868, s18211 and s21922. The row's family name must pass the check that every row's family is a key of the test_guard families. Test file: `hooks/test_mutate_ci.py`.
