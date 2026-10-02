# One check catches a merge or branch that silently undoes earlier work

## The ruling

`lint/check_silent_undo.py` is the one home. CI runs it on each pull request.
`merge/merge.py` calls it through `undo_check` before it pushes or merges.
It reads two things.

- **Reversal.** Landing the branch on upstream puts a file back as an earlier
  first-parent commit of upstream (window 60) had it. Exact blob (whole file), or
  a `-U0` hunk that is that commit's hunk reversed. Catches `git revert` of a merged
  PR and a stale copy carried in by a merge.
- **Lost line.** A merge commit in the branch loses a line one parent added since the
  merge base. Catches a conflict taken "ours" and a hand edit of a merge.

The escape is the trailer `Drops-lines: <path>`, one per path, on any commit of the
branch. A commit message that only names the file does not pass.

## The stale green PR

The owner's first problem: an older PR overwrites a newer change to the same file.
The agent resolves a conflict to its own side, or writes the whole file from an old copy.

- `merge/merge.py` runs the check in `confirm`, before the claim and any push, and again
  after the post-wait fetch of the base tip, right before `gh pr merge`. A red at the
  second run reverts the claim. Unknown refuses too.
- The result is read against the latest upstream tip, never against the merge base.
- The window is 60 commits or every commit upstream gained since the branch was cut,
  whichever is more. An old branch reads all of main's newer work.

## Three shapes that passed Banchi's guard (its DEBT19)

- **Age.** A branch older than the window. Closed by the widened window above.
- **Re-wording.** A restored block with one line changed. A reversal now counts when all
  but one line of an earlier hunk (3 lines or more) come back or go away. Two changed
  lines are a new edit. This is a dial. It is set at one line and stays there until a
  measured case says otherwise.
- **Widened hunk.** A reversal that shares a hunk with a real edit. The read counts lines
  across all hunks of the file, so hunk shape no longer hides it.

## Which design won

Two sources existed. Banchi `scripts/revert-audit.py` compares with earlier commits.
q_max `merge-lost-lines.mjs` compares the parents of one merge.

- Banchi's reader is the base. It is the only one that sees a squash or a single-parent
  commit that carries a stale file. That was the real incident. q_max cannot see it,
  because the merge base already holds the lost work.
- q_max's reader is kept for merge commits. Only it sees a line that a merge removed
  while the rest of the file still looks right.
- From q_max: the `Drops-lines` trailer, and a shallow history is not trusted.
- From Banchi: the landing tree (`merge-tree`, or the branch diff when it conflicts).
- Dropped from Banchi: "a message that names the file passes". A name in a message does
  not state intent. Also dropped: the note-only tier for a partial reversal, and the
  `PKMNSCAN_REVERT=off` switch. A switch that stops the check is not an escape.
- Dropped from q_max: a conflict region is not excused, because a conflict taken "ours"
  is the incident. Also dropped: token-level rewrite rules and rename tracking.

## False alarms handled

- Whitespace and blank lines never count, in either read.
- A move is not a loss. A removed line that the change adds to another file is excused.
  That also covers a rename and a reorder.
- A re-wrapped prose line is not a loss. The line must still read as a run in the new file.
- A rewrite by the resolver is not a loss. Half of the line must survive in a line
  the merge gained.

## Unknown is red in CI

No upstream, a shallow clone, or a failed git read prints UNKNOWN. Locally it exits 0.
With env `CI` or `--strict` it exits 1. `merge.py` refuses on unknown, because its merge
cannot be taken back. This follows decisions/ci-unknown-is-red-and-dedup.md on PR 226.

## Measured on this repo

HISTORY_PLACEHOLDER

## Known limits

- A reversal older than the window is not seen. `--window 0` reads all history.
- A reversal that also rewrites a line is a new edit, not a reversal.
- A line that a resolver half-rewrote passes. The merge is then a judgement call.
- A binary file is not read.
- A merge of three or more parents is UNKNOWN.
