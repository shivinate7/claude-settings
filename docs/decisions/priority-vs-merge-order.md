# A ready priority row goes before a lower pull request

## The ruling

`merge N --confirm --priority-rows FILE` reads the rows of FILE with the standing reader (`priority_row` and `priority_verdict`, the same as `merge --priority-rows FILE`; step `priority-vs-merge-order`). It refuses to merge pull request N when N is not a row's own pull request or branch and some row's pull request reads ok (ready, clean, newest runs green). The refusal names each ready row's slug and pull request. It names no flag that lifts it: the fix is to merge the ready row first, or to take the row out of the handoff.

Built against one case, the #3302 sequence. The owner's top priority, pull request 3302 (row `ci-speed-stack-4`), sat ready while the combined pull request 3314 was the next merge the batch runner made. `--priority-rows` alone only listed the rows, so nothing stopped the lower merge.

The rules:

- N is a row's own pull request when a `pr:` row names N in this checkout's repo, or a `branch:` row names N's head branch (a `repo:` value on that row must be this checkout's repo). Then N goes, with one line saying so, and no other row is read.
- A row that reads flag, waiting, done or unknown never blocks. Each row's verdict line is printed, so a lower pull request that goes says why. A pull request GitHub cannot be read for is unknown, never ok and never printed as clear.
- No `--priority-rows` given: `priority: no rows given, not checked` is printed, and the merge goes on as before.
- A FILE the reader cannot use refuses, because the runner fixes it locally. That is an empty or missing FILE, a FILE with no `priority:` row, and any malformed row: a line that is no `priority:` row, an empty value, more than one target, or a pr that is not `owner/repo#N` (`pr: #3302`). One line says each malformed row cannot be read and is not clear, and says nothing was merged. That line names the row's slug, or, for a line that is no `priority:` row, its first 60 characters, which can hold a `pr:`. It names the pr only when the pr is the defect (a pr that is not `owner/repo#N`). A row with two targets, or an empty branch or repo value, names no pr. It runs before any row's pull request is read and before the lock. It names no override and no flag that lifts it: the fix is the row. The malformed row is the case that let a ready row go unseen: the check could not tell which row was ready.
- A well-formed row whose pull request read fails stays unknown and does not block, because a network blip must not stop every merge. Its line says unknown, never clear. The own-row exit above still skips every other row, malformed ones too.
- The runner's handoff wiring is the project-ops templates: each merging `--confirm` carries `--priority-rows`, on a file of only the `priority:` rows.
- The check runs before the lock, the claim and any push, so a refusal lands nothing: no merge, no claim on main, no lock held, no ref moved. A draft's `--confirm` is the records step and never merges, so it skips the check.
- `merge --priority-rows FILE` alone behaves as before, and still stands alone. With a pull request number and `--confirm`, the flag goes with them.

Cost: the reads `priority_judge` already makes for `merge --priority-rows FILE`: at most two reads per `pr:` row. For `branch:` rows, at most one shared read of the open pull list per run (one call per page). After that, a branch row takes at most two reads when an open pull request matches, or at most one closed read when none does. Those reads are none when N is itself a row or a row is malformed. At most one short `git rev-parse` per run (`priority_here`, which also reads git's config file for the origin). Plus at most one per branch row with no open pull request whose newest closed pull request merged into main (`priority_closed_branch`). No timer, no lock, no file write. Test: `merge/test_priority_vs_merge_order.py` counts the reads and checks that a refusal moves nothing.

Kind: build
Plan: docs/decisions/priority-vs-merge-order.md#the-ruling (all)
Home: merge/merge.py
