# A worker thread outruns its worktree

**What.** `merge.bounded()` lets the debt lint thread (`debt_verdict`) keep reading the worktree after its 5400 s bound passes. The `finally` blocks of `draft_step` and `fast_checks` then drop that worktree. The docstring of `bounded` states this limit.

**Where.** `merge/merge.py`: `bounded`, `debt_verdict`, `pre_ready_rows` (which passes it `wt`), and the `finally` blocks of `draft_step` and `fast_checks` that call `drop_worktree`.

**Decision.** `lanes-run-no-full-ci-job` (a lane runs no full CI job; the ready checks).

**Retire.** Closed when `merge/test_ready_thread_worktree.py` shows that the thread cannot touch a dropped worktree. The closing PR adds that file.
