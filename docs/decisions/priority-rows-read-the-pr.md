# A priority row names its pull request, and each wake reads it

## The ruling

Each wake, the batch runner runs `merge --priority-rows FILE` on the priority rows in its hand-off (step `priority-table-reads-pr`, the check that reads each row's pull request). A row is `priority: <slug> | pr: <owner>/<repo>#<N>` or `| branch: <name>`, and a branch row may add `| repo: <owner>/<repo>`. The command prints one line per row: ok, waiting, done, flag or unknown. It exits 0 only when every row is ok, waiting or done. An empty or missing file exits 1 with `no rows`, never clear.

Built against one incident: pull request 3302, the owner's top priority, sat as a draft and then dirty from 18:40 to 20:27 CST on 2026-11-13, unseen for about two hours, because its row named no branch.

The verdict rules:

- A row that names no pr or branch is a flag: the check cannot read it, and no read is made.
- A row that names more than one pr or branch target is unknown ("row names more than one target"), and neither is read.
- A read that fails, a repo that is not this checkout's (a branch row's `repo:` too, with no read at all), and a merge state GitHub has not computed are unknown, never ok. So is a ready clean head with no run.
- A merged pull request is done only when it merged into main. One merged into another base is a flag ("merged into <base>, not on main"). A closed pull request that did not merge is a flag ("closed, not on main"), never done.
- A draft, a dirty head, a head behind its base and a blocked one are flags, from the pull request read alone. A draft that is also dirty prints both. An unstable or clean head is judged by the newest run per name: red is a flag, pending is waiting, green is ok.
- A branch with no open pull request is judged by its newest closed one: merged into main is done, merged elsewhere or closed is a flag, none is a flag ("no pull request has the head").

Cost: at most two reads per `pr:` row, the runs read only when the verdict needs it. A branch row costs one shared read of the open pull list per wake, then two reads when an open pull request matches, or one closed read (`pulls?state=closed&head=<owner>:<branch>&per_page=1`) when none does. No timer, no process, no lock, no file. It runs only at the wake that already runs. Test: `merge/test_priority_rows.py` counts the reads.

Kind: build
Plan: docs/decisions/priority-rows-read-the-pr.md#the-ruling (all)
Home: merge/merge.py
