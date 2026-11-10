# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3pjhuGumnmrJ5gvqd

## Reply at 2026-11-10T17:28:21Z UTC

IDLE (B)
Goal: re-point the merge.py line cites in decision claims-carry-backing (lines 54, 56-60, 88), so each cite shows the code that backs its claim. PR #1634 had moved those merge.py lines.
Repo shivinate7/claude-settings, branch claims-backing-repoint, draft PR #1765, head 1d370a02b9db1423f16131db02123ecff716f97f, built on main 394ad4863. One commit, docs-only, 7 lines changed in docs/decisions/claims-carry-backing.md.
State: reviewer haiku round 1 PASS. stale_cites --range PASS. ste_lint PASS. merge --lane-lint 1765 PASS. The merge tool posted the review record (kind docs-only, guard no). Handed to batch runner session_013NEJL2vsmyKzJm8jUDt6za on 2026-11-07 21:49 CST. At 11:06 CST on 2026-11-10 it was not on main. Nothing is unpushed.
Left: the PR is two days behind main. Rebase it, then re-read each cited merge.py range, because later merges may have moved those lines again. If any moved, re-point those cites. Then the runner merges.
Findings sent to the coordinator for triage (not built): (1) cited_excerpt in lint/stale_cites.py jumps to a symbol only for a `test path::name` cite. A `read path::name` cite shows the top of the file, so symbol anchors cannot yet replace line ranges. Making cited_excerpt use defined_line for such cites would stop this rot. (2) Line 59 says "every line not judged" is counted, but an exception after a model call (merge.py prose_judge_run) counts no lines.

