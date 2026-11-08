# A shallow clone is never linted at push

**What.** `lint/check_silent_undo.py` reads any shallow clone as UNKNOWN. A cloud lane starts as a depth-50 clone, so rule `lane-lint-push` never lints its silent-undo step there. Each push is allowed with one unknown note, until the lane runs `git fetch --unshallow origin`. The gap rule `lane-lint-push` was built to close stays open on every cloud lane, and the note repeats on each push.

**Where.** `lint/check_silent_undo.py`, `check` and `history` (the shallow test); `hooks/guard_merge.py`, `_lane_read`.

**Decision.** lane-lint-at-push (the lane lint's fast steps run before a push leaves).

**Retire.** A push from a shallow clone is linted: the guard or the check reads the range it needs, or the clone gains the history it needs first. A case in `hooks/test_guard_lane_lint_push.py` pushes a silent undo from a shallow clone and is refused.
