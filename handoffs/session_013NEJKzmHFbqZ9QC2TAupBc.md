# lane: review-record-post-check (session_013NEJKzmHFbqZ9QC2TAupBc), received 09:50 CST 2026-11-10, kind B

(B) Handoff from lane review-record-post-check (session_013NEJKzmHFbqZ9QC2TAupBc). Nothing is unpushed.
- Work: a review record that does not parse now names its earliest bad line. `review_parse` and `review_bad_text` in merge/merge.py; the guard's form refusal, `merge --reviewed` and the `--fix-check` refusal use them.
- Repo shivinate7/claude-settings, branch review-record-post-check, PR #2219 (draft), head ad4fe7b67f3b205e07f75f5a79f8f017b3b016dc. It merges after #2161 (base record-edit-reads-old-body).
- State: reviews done; the done record is comment 6726227616 (round 3 sonnet PASS, net value zero). Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za). Triage folded the step into review-record-parse-warn (session_013NEJL2g4J2bZLchTFF8RGp), which has the hand-off.
- Left: #2219 waits for the #2161 stack and a batch CI run. review-record-parse-warn owns parts 1 and 2: `--lane-lint` refusing an unparsed record or a missing record at the live head, and the comment id in `--reviewed`. One step is still to queue: step:push-branch-held-elsewhere (refuse a push that moves a branch another worktree has checked out).
