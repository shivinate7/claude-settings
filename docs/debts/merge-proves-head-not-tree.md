# The merge check proves the branch head, not the merged tree

**What.** A merge is checked on the branch head: its own green run or a lane-lint PASS, and a clean text merge of head and base (`git merge-tree --write-tree`; a conflict refuses). No suite runs on the merged tree. So a PR that merges cleanly onto a main that has moved can redden main. Seen Nov 24 2026 with PR 3845.

**Where.** `merge/merge.py` (the confirm path and its merge-tree check).

**Decision.** `merge-needs-current-base` (the clean merge check and its cost line).

**Retire.** None yet. Close when the merge runs the suites the merged tree reaches, or when a red main after a merge is reverted first (`git-red-main-reverts`).

Fix: none built.
