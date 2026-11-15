# The unknown-read lint check went red once with nothing wrong

**What.** The lint check "Unknown-read contract (guard + session_start)" printed FAIL "wrote to stderr" for members caseF4 and caseF6 in the lane lint of PR 3492 (runner 10's lane pull request). The log is lint3492b.log, lines 5395 and 5398, 09:29 CST Nov 15. Three lints ran at once on one container. It passed in two solo re-lints of the same head (09:41 and 10:05 CST) and in the PR lane's own container. One sighting. Cause: unmeasured. Runner 10 guesses load, since caseF6 is timeout-based. Parallel lints on one container are normal for the lint runner (runner 10's word, relayed by triage), so Claude is likely to meet this again. Harm: a check that goes red when nothing is wrong teaches the reader to scroll past it (rule `verification-cry-wolf-guard-is-spent`). Source: runner 10, through triage and the consultant, 10:12 CST. Candidate cause, unmeasured: both cases write fixed temp file names that parallel runs share.

**Where.** `lint/check_unknown_reads_contract.py`, the check. Its members caseF4 and caseF6 are in `hooks/test_install_src.sh`.

**Decision.** none. The open roadmap step `unknown-read-lint-flake` (measure the lint flake) holds the sighting and the ask to measure.

**Retire.** Closes when the cause is measured and the check passes under parallel lints on one container. A run of `hooks/test_install_src.sh` under load shows it closed.
