# The unknown-read lint check went red once with nothing wrong

**What.** The lint check "Unknown-read contract (guard + session_start)" printed FAIL "wrote to stderr" for members caseF4 and caseF6 once, in the lane lint of PR 3492 (a lane pull request that the batch runner, runner 10, linted), while three lints ran at once on one container. It passed in two solo re-lints of the same head and in the pull request's own container, and the cause is unmeasured.

**Harm.** A check that goes red when nothing is wrong teaches the reader to scroll past it (rule `verification-cry-wolf-guard-is-spent`). Parallel lints on one container were normal for the batch runner on Nov 15, so Claude is likely to meet this again.

**Source.** The batch runner's log lint3492b.log, lines 5395 and 5398, 09:29 CST Nov 15. The solo re-lints ran at 09:41 and 10:05 CST. One sighting. The coordinator relayed these words from the batch runner. Neither triage nor this record's writer read the log.

**Candidate cause, unmeasured.** The batch runner guesses load, since caseF6 is timeout-based. Another candidate: both cases write fixed temp file names that parallel runs share.

**Where.** `lint/check_unknown_reads_contract.py`, the check. Its members caseF4 and caseF6 are in `hooks/test_install_src.sh`.

**Decision.** none

**Retire.** Closes when the cause is measured and a new case in `hooks/test_install_src.sh` runs caseF4 and caseF6 at the same time and passes. That case shows it closed. The open roadmap step `unknown-read-lint-flake` (measure the lint flake) holds the sighting and the ask to measure.
