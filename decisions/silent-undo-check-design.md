# One check catches a merge or branch that silently undoes earlier work

## The ruling

`lint/check_silent_undo.py` is the one home. CI runs it on each pull request with `--strict`.
`merge/merge.py` calls it through `undo_check` before it pushes or merges. It reads two things.

- **Reversal.** Landing the branch on upstream puts a file back as an earlier first-parent commit of
  upstream had it. The proof is one of three:
  - The exact blob (whole file).
  - A `-U0` hunk reversed on all but one line.
  - Lines main only added that the change removes, even in a hunk that also edits a neighbour.

  It catches `git revert` of a merged PR and a stale copy. It catches a rebase that took its own side
  when the lost work is the rebase-base commit or later. The branch check has no time bound and no
  commit-count floor.
- **Lost line.** A merge commit in the branch loses a line one parent added since the merge base. It
  catches a conflict taken "ours" and a hand edit of a merge. A line main only gained is main's. A line
  a commit added on the branch alone is the branch's.

The escape is the trailer `Drops-lines: <path> -- <reason>`, one per path, on any commit of the branch. A
bare path excuses nothing. Each use prints `ALLOWED <path>: <reason>`. A commit message that only names
the file does not pass. A junk reason passes, so the reviewer reads every reason. There is no switch that
turns the check off.

**The window starts at the fork point,** not at the plain merge-base, which moves to main's tip once the
branch merges main. There is no `--since` time. Reason: a commit-time window let the same shape pass or
fail by its timestamp, and a commit-count floor read old main work that a branch may remove on purpose.

- Fork point: `merge-base(upstream, own[-1] + "^")`, where `own` lists the branch's first-parent commits
  that upstream lacks, newest first. With no merge-base there, the plain merge-base is used.
- The read covers upstream's first-parent commits from the tip down to the fork commit, and the result is
  read against upstream's tip. A conflict leaves no result. Then the branch's own diff is read off the
  plain merge-base.
- A branch cut at main's tip that undoes the tip commit is flagged, a deliberate revert included, which
  needs the trailer. Main work before the fork commit is not read, unless the fork point is off
  upstream's first-parent line. `test_main_work_before_the_cut_is_not_read` pins this.

**Required or advisory.** The check is required here, where lanes are short and land through integration
batches. It is advisory in a repo whose long-lived lanes merge main in and then edit main's lines. Advisory
means that the check runs and prints its flags. The batch reviewer marks each flag real or deliberate, and
a real flag blocks the merge. Move to required when a rule separates a deliberate edit of main's lines
from a stale overwrite, with every incident fixture still red.

**The stale green PR.** An older PR overwrites a newer change to the same file. The agent resolves a
conflict to its own side, or writes the whole file from an old copy. `merge/merge.py` runs the check in
`confirm`, before the claim and any push. It runs it again after the post-wait fetch of the base tip,
right before `gh pr merge`. A red at the second run reverts the claim. Unknown refuses too. Two changed
lines are a new edit, so the reversal dial stays at one line until a measured case says otherwise.

**What is not a loss.**

- Whitespace and blank lines never count.
- A move, a rename or a reorder: a removed line that the change adds to another file is excused.
- A re-wrapped prose line, when the whole line is a run of the new lines with whitespace collapsed. A
  short line never passes as a re-wrap.
- A rewrite by the resolver, when a line of the same hunk reads very much like it. A merge that only adds
  tokens to a line (a new argument) is a rewrite when the line starts the same way and adds no negation.
- A stale value put back is a reversal, never a rewrite. A similar line excuses a drop only when it
  differs from both the lost line and the base line, and its operators and negation match the lost line.
  Numbers may differ only when both sides changed the base line (a third value).

The check prints every flagged line in full, with no cap.

**Unknown is red in CI.** No upstream, a shallow clone, a merge of three or more parents, an old git, or a
failed git read prints UNKNOWN. Locally it exits 0. With env `CI` or `--strict` it exits 1
(ci-unknown-is-red-and-dedup). `merge.py` refuses on unknown, because its merge cannot be taken back. The
way out that does not depend on the check is the owner flag
`merge <pr> --confirm --undo-check-unknown-ok "<reason>"`. It is logged and never excuses a finding.

Kind: process
Home: lint/check_silent_undo.py
