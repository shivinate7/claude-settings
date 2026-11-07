# The report guard does not count a merge made through gh api

- **What.** A turn that merges with `gh api -X PUT repos/o/r/pulls/N/merge` or `gh api repos/o/r/merges` lands a commit. The report guard reads only `gh pr` verbs and the GitHub MCP tools, so the turn ends with no report. Roadmap step report-guard-landing-tools (the Stop report guard covers every landing tool).
- **Where.** `lint/report_guard.py` (`_segment_lands_a_gh_write`, `GH_LANDING_PR_VERBS`).
- **Decision.** `none`.
- **Retire.** `_segment_lands_a_gh_write` counts a `gh api` call whose route ends `/merge` with a PUT, or `/merges` with a POST, and a test in `lint/test_report_guard_landing.py` pins both.
