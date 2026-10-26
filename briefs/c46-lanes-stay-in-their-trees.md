# c46. Lanes start only in the tool's own worktrees, and a dropped lane keeps its branch

Paste this whole file into one fresh claude-settings session (Windows). Written by the advisor,
Oct 26, against main 149f4bc5 (#574). Two lanes, one integration PR, usual rules
(git-integration-branch-merge, roles-review-cap-three). Run after goal 3 and c44 land, or as
a lane beside c44 if it touches no c44 file.

## Lane 1. Refuse a hand-made lane worktree (debt agents-write-main-clone)

Owner ruling, Oct 21, recorded in the debt, not built at 149f4bc5 (no hand-made check in
hooks/guard.py). Incident, Oct 20: an orchestrator whose `isolation: 'worktree'` failed made lane
trees by hand and spawned agents without isolation; two agents wrote into the main clone.

1. Block: the guard refuses the workaround, so a writing lane starts only through the tool's own
   isolation. Find the cheapest reliable predicate first (an Agent or Task call with no
   isolation whose brief names a worktree path outside `.claude/worktrees/`, or a `git worktree
   add` from an orchestrator into a scratchpad). Read the act, not a guess from location
   (decision predicate-is-the-act). Red case first, then green.
2. Diagnose: when the tool's isolation is refused, log which layer refused (harness or guard) and
   its message on the guard's existing refusal line. If the guard refused, fix the guard.
3. Retire the debt per its Retire line.

## Lane 2. The merge tool keeps a dropped lane's branch (debt merge-deletes-dropped-lane)

Incident, Oct 23: batch #564 lost five dropped lanes' branches after merge; restored by hand.
merge/merge.py cuts every lane merged into the batch, including one the batch later reverted.
Fix: keep a lane branch whose merge into the batch was reverted on the batch. Red fixture
test, then green. The other merge-tool lane debts (ff-first-lane-not-a-tip,
squash-lane-branch-kept, lane-cycle-delete-order, long-lived-head-lost-in-batch) stay notes
unless the same edit fixes one for free; say which.

## Report

Per the report rules, with the four pace numbers.
