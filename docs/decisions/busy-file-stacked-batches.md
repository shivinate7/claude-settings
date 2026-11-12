# Lanes that change the same busy file go in back-to-back stacked batches

## The ruling

A busy file is a file that many lanes change at once, so two lanes that change it conflict. The repo names its busy files in `merge.busyFiles` in `.github/stamp.json`, a list of path patterns. The default is none.

- A new `merge --batch-build NAME PR...` is refused when two or more lanes in the request each change the same file that matches `merge.busyFiles`. Nothing is pushed. The refusal names the file and the lanes.
- The batch runner builds one lane, or one group, as batch NAME, then builds the others as the next batch with `--on batch-NAME`, on the running batch's head. A conflict in one batch then drops no lane of the other.
- A file shared by two lanes counts only when both lanes change it beyond what they share: a lane stacked on another, and two lanes stacked on a third, do not collide through the stack. A rename or a delete of the file counts as a change. A git read that fails refuses the build.
- A repeat build of a frozen set, `--ready` and `--batch-drop` run no check. The check reads one request: two lanes in two separate batches built from main are not compared.

This repo's busy files: `hooks/guard.py`, `hooks/test_guard.py`, `hooks/mutate_guard.py`.

Where it lives: `busy_file_lanes` in `merge/merge.py`, the merge tool's one home for batch builds. No second copy.

Why: plan R26 part 4. Two lanes were dropped from 5 or more batches each, and 147 lane drops became 15 merges (audit 09:37 CST Nov 11, last 15 batch merges). Owner 13:15 CST Nov 12 asked for a faster merge queue.

Sources: owner, plan R26 part 4 (box answer 10:05 CST Nov 11, "Both"); owner ruling R55, 13:21 CST Nov 12, as relayed by the coordinator.

Kind: process
Home: merge/merge.py
