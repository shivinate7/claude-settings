# report-guard-carried-review

**What.** After PR #3388 (the merge tool carries a review log and a lane-lint PASS to a replacement PR by tree sha), the lane Stop hook still reads only a PR's own issue comments. A carried PR gets REVIEW_NO_RECORD there, although `merge --reviewed` reads it done. A lane with a carried log is refused at Stop until it posts a log of its own.

**Where.** `lint/report_guard.py`, the review-record read (`_newest_record`, `_live_state`). The carry lives in `merge/merge.py` (`live_review_state` with a named source, `replaces_source`).

**Decision.** `pr-review-record` (a review log names the head it reviewed, and only an open pull request takes one).

**Retire.** `_live_state` makes the source-aware `live_review_state` read, and a new case in `lint/test_report_guard_review.py` shows a carried PR reads done at Stop: `lint/test_report_guard_review.py`.
