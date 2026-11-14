# A worker thread outruns its worktree

**What.** `merge.bounded()` lets a worker thread that outran its bound keep running. The bound is 5400 s for the debt lint (`debt_verdict`) and 480 s for the open-PR clash check (`clash_verdict`). Such a thread can keep reading the worktree that `draft_step`'s `finally` then drops. The docstring of `bounded` states this limit.

**Where.** `merge/merge.py`: `bounded`, `debt_verdict`, `clash_verdict`, and the `finally` of `draft_step` that calls `drop_worktree`.

**Decision.** `lanes-run-no-full-ci-job` (a lane runs no full CI job; the ready checks).

**Retire.** Closed when `merge/test_ready_thread_worktree.py` shows that the thread cannot touch a dropped worktree. The closing PR adds that file.
