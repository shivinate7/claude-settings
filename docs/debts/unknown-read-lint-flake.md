# The unknown-read lint check went red once with nothing wrong

**What.** The lint check "Unknown-read contract (guard + session_start)" printed FAIL "wrote to stderr" for two of its members, caseF4 and caseF6, in the lane lint of PR 3492. Source: runner 10's log lint3492b.log, lines 5395 and 5398, 09:29 CST on Nov 15. Three lints ran at once on one container. The same check passed in two solo re-lints of the same head (09:41 and 10:05 CST), and in the PR lane's own container, where both cases were ok. One sighting. The cause is unmeasured. Runner 10 guesses load, since caseF6 is timeout-based; nothing was measured. Parallel lints on one container are normal for the lint runner, so Claude is likely to hit this again. The harm: a check that goes red when nothing is wrong teaches the reader to scroll past it (rule `verification-cry-wolf-guard-is-spent`, a guard that cries wolf is spent). Source for all facts: runner 10, relayed by triage and the consultant at 10:12 CST, none re-read by this record's writer.

**Where.** `lint/check_unknown_reads_contract.py`, the check. Its members caseF4 and caseF6 are in `hooks/test_install_src.sh`.

**Decision.** none. The open roadmap step `unknown-read-lint-flake` (measure the lint flake) holds the sighting and the ask to measure.

**Retire.** Closes when the cause is measured and the check passes under parallel lints on one container. A run of `test_install_src.sh` under load shows it closed.
