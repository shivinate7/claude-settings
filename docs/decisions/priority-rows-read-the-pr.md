# A priority row names its pull request, and each wake reads it

## The ruling

Each wake, the batch runner runs `merge --priority-rows FILE` on the priority rows in its hand-off (step `priority-table-reads-pr`, the check that reads each row's pull request). A row is `priority: <slug> | pr: <owner>/<repo>#<N>` or `| branch: <name>`. The command prints one line per row: ok, waiting, done, flag or unknown. It exits 0 only when every row is ok, waiting or done. An empty or missing file exits 1 with `no rows`, never clear.

Incident: pull request 3302, the CI-speed stack, the owner's top priority, sat as a draft and then dirty from 18:40 to 20:27 CST on 2026-11-13. Its priority row named no branch, so nothing read its pull request. The owner's top priority went unseen for about two hours.

Judged by the outcome: a row that names no pr or branch is a flag, because the check cannot read it. A read that fails, a repo the checkout cannot read, and a merge state GitHub has not computed are unknown, never ok.

Deviations from the first plan:

- A closed pull request that did not merge is a flag ("closed, not on main"), not done. A replaced pull request is not landed work.
- A `pr:` row costs at most two reads, not one: the pull request, then the runs on its head. The runs are read only when the verdict needs them, so a merged, closed, draft, dirty, behind or unknown row costs one.

Cost: at most two reads per `pr:` row, plus one shared read of the open pull list per call when a row names a branch. No timer, no process, no lock, no file. It runs only at the wake that already runs. Test: `merge/test_priority_rows.py` counts the reads.

Kind: build
Plan: docs/decisions/priority-rows-read-the-pr.md#the-ruling (all)
Home: merge/merge.py
