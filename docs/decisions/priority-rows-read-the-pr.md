# A priority row names its pull request, and each wake reads it

## The ruling

Each wake, the batch runner runs `merge --priority-rows FILE` on the priority rows in its hand-off (step `priority-table-reads-pr`, the check that reads each row's pull request). A row is `priority: <slug> | pr: <owner>/<repo>#<N>` or `| branch: <name>`, and a branch row may add `| repo: <owner>/<repo>`. The command prints one line per row: ok, waiting, done, flag or unknown. It exits 0 only when every row is ok, waiting or done. An empty or missing file exits 1 with `no rows`, never clear.

Built against one incident. Pull request 3302, the owner's top priority, sat as a draft and then dirty from 18:40 to 20:27 CST on 2026-11-13. It went unseen for about two hours, because its row named no branch.

The verdict rules:

- A row that names no pr or branch is a flag: the check cannot read it, and no read is made.
- A row that names more than one pr or branch target is unknown ("row names more than one target"), and neither is read.
- A row with an empty `branch:` or `repo:` value is unknown ("row names an empty value"), and nothing is read.
- A read that fails, a repo that is not this checkout's (a branch row's `repo:` too, with no read at all), and a merge state GitHub has not computed are unknown, never ok. So is a checkout whose repo cannot be named: no pr or branch row is read. So is a ready clean or blocked head with no run.
- A merged pull request is done only when it merged into main. One merged into another base is a flag ("merged into <base>, not on main"). A closed pull request that did not merge is a flag ("closed, not on main"), never done.
- A draft, a dirty head and a head behind its base are flags, from the pull request read alone. A draft that is also dirty prints both. An unstable or clean head is judged by the newest run per name: red is a flag, pending is waiting, green is ok.
- A blocked head is judged by its runs too, since GitHub reads blocked while a required run is still going. Red is a flag, pending is waiting, and no run is unknown. All green is a flag ("blocked").
- A branch with no open pull request is judged by its newest closed one: merged into main is done, merged elsewhere or closed is a flag, none is a flag ("no pull request has the head"). Merged into main is a flag instead ("branch reused after merge, no open PR") when the local `origin/<branch>` ref names a sha other than that pull request's head. A missing ref, or a git read that fails, counts as no ref.

Cost: at most two reads per `pr:` row, the runs read only when the verdict needs it. A branch row costs at most one shared read of the open pull list per wake. It then costs at most two reads when an open pull request matches. When none does, it costs at most one closed read (`pulls?state=closed&head=<owner>:<branch>&per_page=1`). When that pull request merged into main, it adds a local `git rev-parse` of the origin ref, which reads no network and writes nothing. No timer, no process, no lock, no file. It runs only at the wake that already runs. Test: `merge/test_priority_rows.py` counts the reads.

Kind: build
Plan: docs/decisions/priority-rows-read-the-pr.md#the-ruling (all)
Home: merge/merge.py
