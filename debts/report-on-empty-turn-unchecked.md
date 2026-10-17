# A write-up on a turn where nothing landed is not seen

- **What.** The report gate returns early when nothing landed, so it cannot see a report written on such a turn. The rule `reports-no-report-when-nothing-landed` has no check.
- **Where.** `lint/report_gate.py`, rule `reports-no-report-when-nothing-landed`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** The report gate flags a report on a turn where nothing landed, and a test in `lint/test_gates.py` goes red on one.
