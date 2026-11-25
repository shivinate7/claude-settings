# A draft's --confirm checks the head, not the merged tree

**What.** `merge <pr> --confirm` on a draft runs the ready checks on the head alone when the head lacks main's tip but merges cleanly. Only `merge <pr> --ready` builds the merge with main first and checks that tree. So a lint that fails only on the merged tree passes `--confirm` and is caught only on `--ready`. The ruff errors of pull request 3856 (Nov 24 2026, a function defined twice after a merge of main) are that kind of failure.

**Where.** `merge/merge.py`, `draft_step()` at :5571 (the merge with main runs only under `merge_main`, passed by `--ready` at :8550), and the confirm path at :5604-5616, where the ready checks run on `wt` with no merged tree. The clean-merge proof is `holds_base()` at :2585-2588 (rule M3).

**Decision.** `merge-needs-current-base` (rule M3: a clean merge proves the tip adds no clash; it does not run the ready checks on the merged tree).

**Retire.** `merge/test_merge.py` gets a red case: a draft's `--confirm` whose head merges cleanly with main, and fails a lint only on the merged tree, is refused before the mark.
