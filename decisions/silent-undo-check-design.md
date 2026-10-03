# One check catches a merge or branch that silently undoes earlier work

## The ruling

`lint/check_silent_undo.py` is the one home. CI runs it on each pull request.
`merge/merge.py` calls it through `undo_check` before it pushes or merges.
It reads two things.

- **Reversal.** Landing the branch on upstream puts a file back as an earlier
  first-parent commit of upstream had it. The proof is one of three. The exact blob
  (whole file). A `-U0` hunk reversed on all but one line. Lines main only added that the
  change removes, even in a hunk that also edits a neighbour. The third is the rebase that
  took its own side. Catches `git revert` of a merged PR and a stale copy.
  Only commits upstream gained after the branch was cut are read. That means since the merge
  base, or since the branch's first commit was authored. A rebase keeps that date.
  There is no 60-commit floor. The floor read old main work that a branch may remove on purpose.
- **Lost line.** A merge commit in the branch loses a line one parent added since the
  merge base. Catches a conflict taken "ours" and a hand edit of a merge.

The escape is the trailer `Drops-lines: <path> -- <reason>`, one per path, on any commit of the
branch. A bare path excuses nothing. Each use prints `ALLOWED <path>: <reason>`. A commit
message that only names the file does not pass.

## The stale green PR

The owner's first problem: an older PR overwrites a newer change to the same file.
The agent resolves a conflict to its own side, or writes the whole file from an old copy.

- `merge/merge.py` runs the check in `confirm`, before the claim and any push, and again
  after the post-wait fetch of the base tip, right before `gh pr merge`. A red at the
  second run reverts the claim. Unknown refuses too.
- The result is read against the latest upstream tip, never against the merge base.
- An old branch reads all of main's newer work, by commit count since the merge base or by
  date since the branch's first commit.

## Three shapes that passed Banchi's guard (its DEBT19)

- **Age.** A branch older than a window. There is no window now. Closed.
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
- A rewrite by the resolver is not a loss. A line of the same hunk must read 0.9 like it.
  0.8 would excuse `A new 1` against `B new 1` (0.86), which is a drop.

## Unknown is red in CI

No upstream, a shallow clone, or a failed git read prints UNKNOWN. Locally it exits 0.
With env `CI` or `--strict` it exits 1. `merge.py` refuses on unknown, because its merge
cannot be taken back. The way out that does not depend on the check is the owner flag
`merge <pr> --confirm --undo-check-unknown-ok "<reason>"`. It is logged and never excuses a
finding. This follows decisions/ci-unknown-is-red-and-dedup.md on PR 226.

## Measured on this repo

Run over main (189 first-parent commits, 2026-10-02): 26 hits. This run used the 60-commit floor and
the older 0.5 rewrite rule. It was not repeated after the fixes. The owner ruled that CI runs the full
suites and no history audit runs locally. The numbers below are unmeasured for the current code.

- 1 lost line: a merge that removed a placeholder entry once the real one landed. Deliberate.
- 25 reversals. Each undoes earlier work by a later commit. The 15 exact ones were read
  one by one: all deliberate (a deleted file, a removed rule, a counter that moved back).
  Of the 10 added by the near-reversal read, 4 were sampled and are real deliberate
  removals. 6 are unread.
- 0 accidental undos found. Every real hit is a deliberate removal that now needs a trailer.
  That cost is the owner's choice. A hit rate of 26 in 189 commits is high, and is the
  price of the near-reversal read (an exact-only read gave 16).

Cost: a pull request run took 0.4 to 5 seconds on this repo. The full-history audit took
2 to 6 minutes (204 merges are read, one `git show` per file).

## Known limits

- A reversal older than the window is not seen. `--window 0` reads all history.
- A reversal that also rewrites a line is a new edit, not a reversal.
- A line that a resolver half-rewrote passes. The merge is then a judgement call.
- A binary file is not read.
- A removal of added lines that shares a hunk with an edit is not seen. An edit in place
  looks the same. Restored lines in a shared hunk are seen.
- A merge of three or more parents is UNKNOWN. So are git older than 2.38, a shallow clone,
  and any history the check cannot read. Aliases and exotic merges count as unknown, not as clean.
  CI is red on unknown. `merge.py` refuses unless the owner passes `--undo-check-unknown-ok`.
- A junk trailer reason passes. `Drops-lines: a.txt -- x` excuses the path. The check prints
  `ALLOWED <path>: <reason>`, so the reviewer reads every reason. A reviewer who does not
  read it is the gap.
- A stale value put back is a reversal, never a rewrite. A similar line excuses a drop only
  when it differs from both the lost line and the base line. A value both sides changed may
  resolve to a third value (0.8 like it). A line main only added needs 0.9.
- A base line plus trailing tokens or punctuation is the base line, so a stale value stays a reversal.
- A similar line never excuses a drop when its operators or negation differ from the lost line.
  Numbers may differ only when both sides changed the base line (a third value).
- A re-wrap passes only when the whole line is a run of the new lines. Whitespace is collapsed.
  The run needs 4 words or more. It must start or end at a line edge.
  A whole added block that survives with only its line breaks moved also passes.
  A short line never passes as a re-wrap.
