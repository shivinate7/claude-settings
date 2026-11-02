# A replay skips a file that does not parse, and its row can still give a rate

- **What.** A file that does not parse is listed as skipped, and its row can still show a kill rate. In the q_max run, seven PRs skipped one file, `harness/browser/verify.test.mjs`, with "Invalid string length" or heap exhaustion. Six of those rows still show a rate. The owner's size range, about 92 to 300 KB, is not measured in the run logs. The cause of the parse failure is unread.
- **Where.** The parse-error skip in `replay_pr` (`hooks/mutate_shared.py`).
- **Decision.** `mutation-report-scores-suites` (the mutation report scores suites).
- **Retire.** Parse the file, or mark its row UNKNOWN instead of a rate. A fixture in `hooks/test_mutate_replay.py` pins the row that holds a skipped file. The q_max profile no longer reads test files as product, which removes this q_max case, but not the general one.
