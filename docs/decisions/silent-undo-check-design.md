# One check catches a merge or branch that silently undoes earlier work

## The ruling

`lint/check_silent_undo.py` is the one home. CI runs it on each pull request with `--strict`.
`merge/merge.py` calls it through `undo_check` before it pushes or merges. It reads three things.

- **Reversal.** Landing the branch on upstream puts a file back as an earlier first-parent commit of
  upstream had it: the exact blob, a `-U0` hunk reversed on all but one line, or lines main only added
  that the change removes, even in a hunk that also edits a neighbour. It catches `git revert` of a merged
  PR, a stale copy, and a rebase that took its own side when the lost work is the rebase-base commit or
  later. The branch check has no time bound and no commit-count floor.
- **Lost line.** A merge commit in the branch loses a line one parent added since the merge base. It
  catches a conflict taken "ours" and a hand edit of a merge. A line main only gained is main's. A line a
  commit added on the branch alone is the branch's. A merge of three or more parents is not read, and the
  check reports it as UNKNOWN only after the other reads finish. The merge tool refuses an UNKNOWN that
  carries a finding, and the reason flag cannot lift it (step notes-union-batch-revival).
- **Revived note.** A note the branch deleted is back at head, because a union merge of main put it back
  (decision `notes-merge-union`). The check replays the branch's own commits and counts copies per note.
  A note is its slug, or its whole line when it has no slug form. A rebase leaves no merge, so it is not read
  (debt `silent-undo-rebase-no-merge`).

The escape is the line `Drops-lines: <path> -- <reason>`, one path per line. `bin/merge` reads it from the
commit trailers of the branch and from the PR body. A bare path excuses nothing, and no reason excuses
nothing. Each use prints `ALLOWED <path>: <reason>`. A junk reason passes, so the reviewer reads every
reason. No switch turns the check off.

A refusal prints the whole remedy, so the author can copy it: a commit message between the lines
`--- begin commit message ---` and `--- end commit message ---`, then the command
`git log -1 --format='%(trailers:key=Drops-lines)'` to run after the commit. Git reads trailers only in a
message's last paragraph, so the `Drops-lines`, `Co-Authored-By` and `Claude-Session` lines sit together in
one paragraph under the subject. `remedy_text()` in `lint/check_silent_undo.py` is the one home of that text.
The CLI and both refusals of `merge/merge.py` `undo_check` (a finding, and an UNKNOWN that carries a finding) print it.
A refusal for an UNKNOWN with no finding names no drop and prints no remedy.

A deleted debt file has a second escape: a `Retire-run: <slug> -- <run URL>` in the PR body's last paragraph
that the debt-close check accepts (decision `debt-close-runs-retire`). It excuses only that debt's path, never
another file, and only a whole delete, not a rename out of `docs/debts/`. Merge tool only: the CLI and CI pass
no PR body, as with a `Drops-lines` line in the body; CI's way out is a `Drops-lines` commit trailer. With no
run reader, or a read that fails, the finding stays. Cost: it runs only in the merge tool, when the scan has a
finding and the body holds a cite. For each flagged cited debt, it runs the debt-close judgment: git reads,
each Retire test in a temporary worktree, and at most one run read. A test proves that
an unflagged close gets no run read. It starts no long-lived process.

- **Body rule.** Drop fenced blocks and `<!-- -->` comments. Skip closing paragraphs that hold only the
  Claude Code attribution line. Read only the last paragraph left, with the trailer rules above.
- **Why the body.** A repo that squashes, or writes its reasons in the PR, could not declare a dropped
  line. A session in another repo that uses `bin/merge` asked for this.
- **Verdict.** When the check finds a dropped line, `bin/merge preview` prints one `BLOCKED: <reason>`
  line and exits 1. An unreadable history is a plain refusal with no BLOCKED line.

**The window starts at the fork point,** not at the plain merge-base, which moves to main's tip once the
branch merges main. There is no `--since` time. Reason: a commit-time window let the same shape pass or
fail by its timestamp, and a commit-count floor read old main work that a branch may remove on purpose.

- Fork point: the merge-base of upstream and the parent of the branch's oldest first-parent commit that
  upstream lacks. With no merge-base there, the plain merge-base is used.
- The read covers upstream's first-parent commits from the tip down to the fork commit, against
  upstream's tip. Main work before the fork commit is not read, unless the fork point is off upstream's
  first-parent line.
- A branch cut at main's tip that undoes the tip commit is flagged, a deliberate revert included, which
  needs the trailer.

**Required or advisory.** The check is required here, where lanes are short and land through integration
batches. It is advisory in a repo whose long-lived lanes merge main in and then edit main's lines.
Advisory means that the check runs and prints its flags. The batch reviewer marks each flag real or
deliberate, and a real flag stops the merge. It moves to required when a rule separates a deliberate
edit of main's lines from a stale overwrite, with every incident fixture still red.

**The stale green PR.** An older PR overwrites a newer change to the same file. `merge/merge.py` runs the
check in `confirm`, before the claim and any push. It runs it again after the post-wait fetch of the base
tip, right before `gh pr merge`. A red at the second run reverts the claim. Unknown refuses too. Two
changed lines are a new edit, so the reversal dial stays at one line until a measured case says otherwise.

**What is not a loss.**

- Whitespace and blank lines.
- A move, a rename or a reorder: a removed line that the change adds to another file.
- A rename git pairs (`-M`, 50% similar or more): the new file is judged on its edits, as if made in place. Below that it stays a delete and an add.
- A re-wrapped prose line. A short line never passes as a re-wrap.
- A rewrite by the resolver, when a line of the same hunk reads very much like the lost line. Adding
  tokens to a line (a new argument, a trailing clause) is a rewrite. A negation voids that only when it sits
  inside the original words (`deploy now` became `deploy not now`). A negation after the last original word
  is new text beside the old, so the line is not lost. Trailing punctuation of the old line is no word.
- A stale value put back is a reversal, never a rewrite. A similar line excuses a drop only when it
  differs from both the lost line and the base line, and its operators and negation match the lost line.
  Numbers may differ only when both sides changed the base line (a third value).

**Unknown is red in CI.** No upstream, a shallow clone, a merge of three or more parents, an old git, or a
failed git read prints UNKNOWN. Locally it exits 0 unless the UNKNOWN carries a finding. With env `CI` or `--strict` it exits 1
(ci-unknown-is-red). `merge.py` refuses on unknown, because its merge cannot be taken back. The
way out that does not depend on the check is the reason flag
`merge <pr> --confirm --undo-check-unknown-ok "<reason>"`. Claude may type it, with a reason (owner
ruling, Cockpit item 178 a, 2026-11-03 22:31 CST). Each lift is printed and written to the merge
commit message as `Reason flag: --undo-check-unknown-ok: <reason>`. It never excuses a finding.

Kind: process
Home: lint/check_silent_undo.py
