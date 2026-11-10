# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2mzycmcUKim3G7RkZ

## Reply at 2026-11-10T17:27:19Z UTC

IDLE (B) — lane job-cap-expressions (session_013NEJL2mzycmcUKim3G7RkZ), repo shivinate7/claude-settings.
Goal: step job-cap-expressions. The merge-lock floor (largest job cap + 5) must not read too low when a cap is `timeout-minutes: ${{ matrix.<key> }}`.
State: both PRs are built, reviewed, and pass lane-lint. All commits are pushed. Both are handed to batch runner session_013NEJL2vsmyKzJm8jUDt6za. Both are open drafts on main e2703c611, so they may need a rebase onto current main.
- #1876 (matrix job caps), branch job-cap-expressions, head 7267de93c. Review round 1 haiku FAIL, round 2 sonnet PASS. Record comment 6720408024.
- #1918 (no-config job caps, and the rule in record ci-job-caps), branch job-cap-no-config, head 028d5a4af, Merge after #1876. Review round 1 haiku PASS, fix check haiku PASS. Record comment 6720854938.
Files: merge/merge.py (job_caps, scan_job_caps, matrix_cap, apply_cap_floor, load_config), merge/test_merge.py (Cap* classes), lint/test_rule_audit.py (one exempt entry), docs/decisions/ci-job-caps.md.
Rulings: coordinator 03:35 CST Nov 8, option c. A static matrix list resolves to its max. An unknown expression sets no floor, and prints a line when the repo sets no deadline. Owner item 386 (04:35 CST): the no-config path does the same.
Left: the merge, by the batch runner. Notes (Fix: none, until 2026-11-21) are in PR comments 6720851851 and 6720852306. The guard for the bad review-record mistake is in step review-record-post-parses (#1551).

