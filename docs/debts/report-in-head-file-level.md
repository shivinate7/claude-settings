# The report-in-head check works at file level

**What.** The check shows that each reported file changed from the base, not that each reported edit landed. A builder whose second edit to an already changed file was refused, and who reports it, still passes. A fix round that passes `--base <last reviewed head>` narrows this to the round's own change, but a refused second edit in one round to one file passes too.

**Where.** `lint/check_report_in_head.py`, `pushed_diff` (paths only, no hunks) and `reported_paths` (a `:range` is dropped).

**Decision.** builder-report-in-head (a builder's reported files are checked in the pushed head before review).

**Retire.** The check compares each reported `:range` with the changed line ranges of the pushed diff, or the decision names the file-level gap as accepted and this debt is deleted. A case in `lint/test_check_report_in_head.py` shows a reported range outside the diff's hunks exiting 1.
