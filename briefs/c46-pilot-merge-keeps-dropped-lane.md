# Pilot: the merge tool keeps a dropped lane's branch (c46, lane 2)

For a build thread in the Claude Settings Audit project (cloud). Written by the advisor thread,
Oct 26, against claude-settings main 149f4bc5. This is the pilot for c52 (this project builds
the portable claude-settings backlog as PRs). Owner rulings, Oct 26: this project may push
claude-settings branches and open PRs; it holds the standing merge grant
(decision standing-merge-grant); the advisor thread answers your questions.

## The defect

Debt merge-deletes-dropped-lane. After a batch merges, merge/merge.py (cut_lanes, line ~1023;
lane_tips, line ~1009) deletes the remote branch of every lane merged into the batch, including
a lane the batch later reverted. Batch #564 lost five such branches on Oct 23; they were restored
by hand. A dropped lane needs its branch to rejoin.

## The work

1. Test first: in merge/test_merge.py, a fixture batch with one lane merged and then reverted on
   the batch. After the merge, that lane's branch still exists. Show it red on main.
2. Build: cut_lanes keeps a lane whose merge into the batch was reverted on the batch. Green.
   The four other merge-tool lane debts (ff-first-lane-not-a-tip, squash-lane-branch-kept,
   lane-cycle-delete-order, long-lived-head-lost-in-batch) stay as they are unless the same edit
   fixes one for free; say which.
3. Retire the debt per its Retire line. Do not edit docs/records.md (records-index-at-merge).
4. A fresh reviewer subagent that never saw the build reads the diff (it changes program logic).
   Up to three rounds (roles-review-cap-three).
5. Open the PR, ready, and watch CI (Linux, Mac, Windows) to green.

## Cloud notes

- claude-settings hooks are not installed here, so no guard runs. Follow the CLAUDE.md rules by
  hand. `verdict` may be missing: run the test file directly and give the verdict only.
- The merge is part of the pilot. Check first whether `gh` is logged in here (`gh auth status`).
  In the advisor thread's container it is not. If `gh` works, merge with
  `python merge/merge.py <PR>`. If it does not, do NOT merge with the GitHub button: a button
  merge skips the records page rebuild, the record-number claim and the branch cleanup, and the
  records page on main would go stale. Stop at a green PR and report what blocked the merge.

## Report

Done, Deviations, Input Needed, Next, plus the four pace numbers. Also list each claude-settings
rule that did not fit a cloud thread, and why; each becomes a note on c52.
