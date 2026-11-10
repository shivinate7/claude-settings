# ste-lint-run-exit-codes (session_013NEJKys31F9TckFXjRxWER), received 09:44 CST 2026-11-10, kind B

Handoff (B), lane ste-lint-run-exit-codes (step 791). Nothing unpushed.
1. Work: ste-lint action exit codes. fail:false no longer mutes a stale_cites UNKNOWN or crash; set -e proven by tests; a failing git diff fails the job (history gap stays exit 0). Follow-up: fetch the base with history first, under item 276 a.
2. shivinate7/claude-settings. PR #2262 (draft), branch ste-lint-run-exit-codes, head ed4a70d7a50eddba7a959b5c905c86ccccb958eb. PR #2270 (draft, "Merge after: #2262"), branch ste-lint-fetch-base, head 5498a4d106cfe1c6b7be556ed356de450308aea4.
3. State: both handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) with lane lint PASS. #2270 has its record at the final head (rounds 1-3, net value positive). #2262's record holds rounds 1-3 but no fix check lines.
4. Left: #2262 waits on #1957 (two fix checks per chain, owner item 426 a); then someone runs `merge 2262 --review-record` with fix check 2 at the live head and posts the printed lines only. Then the runner merges #2262, then #2270 (second to land rebases docs/decisions/stale-cites-at-merge.md against #1330).
5. Open notes: scope all git ls-files drops its exit (run.sh 31-36); lint/git_fetch.py docstring names callers that do not call it (fix in #1330, whose file it copies); 300 s fetch timeout; #1330 finding+unread case.
