# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKzBfRycskE32T2Pj9F

## Reply at 2026-11-10T17:23:14Z UTC

IDLE (B) — lane reviewed-sends-back (session_013NEJKzBfRycskE32T2Pj9F).
Goal: `merge --reviewed` prints `send back: #N session_<id> (<reason>)` for each open draft older than 12 h whose newest review record is missing, stale, bad (with its parse error) or for another PR, so the batch runner sends each back to its lane session (owner ask, 2026-11-08 10:15 CST; audit F3).
State: PR #2177, branch lane/reviewed-sends-back, head c26d72f1b (all pushed), draft on base 422cbbdfe. Review done: round 1 FAIL, fix check PASS; both review records are posted on the PR. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-08. CI has not run.
Files: merge/merge.py (REVIEW_SEND_BACK, SEND_BACK_HOURS, review_walk, review_parse_error, reviewed_read(h, now)), merge/test_merge.py (ReviewedSendBack, ReviewParseError), docs/decisions/pr-review-record.md.
Left: rebase onto current main (it has moved far) and re-run merge/test_merge.py; a rebase changes the head, so the review record must be redone (fix check or new round). Related PRs: #2225 (Stop hold, lane idle-lane-archive-at-merge, Merge after #2177) also defines REVIEW_SEND_BACK, and whichever lands second drops its copy. #2163 (reviewed_block) touches other functions.
Filed: step brief-destructive-git (triage, roadmap 4fa94ad65).

