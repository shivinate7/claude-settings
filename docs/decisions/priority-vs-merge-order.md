# A ready priority row goes before a lower pull request

## The ruling

`merge N --confirm --priority-rows FILE` reads the rows of FILE with the standing reader (`priority_row` and `priority_verdict`, the same as `merge --priority-rows FILE`; step `priority-vs-merge-order`). It refuses to merge pull request N when N is not a row's own pull request or branch and some row's pull request reads ok (ready, clean, newest runs green). The refusal names each ready row's slug and pull request. It names no flag that lifts it: the fix is to merge the ready row first, or to take the row out of the hand-off.

Built against one case, the #3302 sequence. The owner's top priority, pull request 3302 (row `ci-speed-stack-4`), sat ready while the combined pull request 3314 was the next merge the batch runner made. `--priority-rows` alone only listed the rows, so nothing stopped the lower merge.

The rules:

- N is a row's own pull request when a `pr:` row names N in this checkout's repo, or a `branch:` row names N's head branch. Then N goes, with one line saying so, and no other row is read.
- A row that reads flag, waiting, done or unknown never blocks. Each row's verdict line is printed, so a lower pull request that goes says why. A pull request GitHub cannot be read for is unknown, never ok and never printed as clear.
- No `--priority-rows` given: `priority: no rows given, not checked` is printed, and the merge goes on as before.
- An empty or missing FILE given on purpose refuses, with "not clear". The runner named a file it cannot supply, and a local fix supplies it.
- The check runs before the lock, the claim and any push, so a refusal lands nothing: no merge, no claim on main, no lock held, no ref moved. A draft's `--confirm` is the records step and never merges, so it skips the check.
- `merge --priority-rows FILE` alone behaves as before, and still stands alone. With a pull request number and `--confirm`, the flag goes with them.

Cost: the reads `priority_judge` already makes for `merge --priority-rows FILE`, at most two per `pr:` row, plus the shared open-pull list read for branch rows. None when N is itself a row. No process, timer, lock or file write. Test: `merge/test_priority_vs_merge_order.py` counts the reads and checks that a refusal moves nothing.

Kind: build
Plan: docs/decisions/priority-vs-merge-order.md#the-ruling (all)
Home: merge/merge.py
