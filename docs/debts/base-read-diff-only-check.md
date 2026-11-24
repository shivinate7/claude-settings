# A diff-only check reads as "this change broke it" on the base

**What.** A ready check that reads only the diff from the base to the head passes on the base commit, because its diff there is empty. So its base row always reads `passes on <sha9>: this change broke it`, even when the check is also broken on main. The base read cannot tell the two apart. Two checks read this way: the Silent undo check (`lint/check_silent_undo.py`, which reads the range from the base to the head), which failed in pull request 3856, and the comment narration check (`lint/check_comment_narration.py`, which reads the diff from the merge base of `origin/<base>`). Claude is likely to hit it in normal work, since a failing check on a lane is the case the base read exists for.

**Where.** `base_read_phrases` in `merge/merge.py`. `lint/check_silent_undo.py`. `lint/check_comment_narration.py`.

**Decision.** `lanes-run-no-full-ci-job` (the ready checks, and the base read paragraph in it).

**Retire.** Closed when a case in `merge/test_lane_lint.py` shows a diff-only check that is broken on the base gets a base row that does not read `this change broke it`, such as `also fails on`, or a row that says the check reads only the diff.
