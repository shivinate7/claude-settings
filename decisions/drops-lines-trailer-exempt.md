# A commit's Drops-lines trailer may name a record path

## The question

Where may a record path appear in a commit message, under the cite-by-id rule?

## The ruling

Owner, 2026-10-12: the `Drops-lines: <record path> -- <reason>` trailer is the one place a
record path is allowed in a commit message. Everything else on that line, and every other
line, is still judged by the cite-by-id rule (CLAUDE.md `git-cite-by-id`; guard rule
`cite-by-id`).

## The incident

The silent-undo check (decision silent-undo-check-design) requires that trailer when a PR
deletes lines from a record. The guard's cite-by-id rule refused any record path in a
`git commit` message, the trailer included. One merge had to be redone as a new PR
(feedback, 2026-10-12). MEASURED 2026-10-12, before this change: `git commit -m` with the
body `x`, a blank line, then `Drops-lines: deferred/env-file-wrappers.md -- reason` was
denied, the same as a prose cite.

## The exemption's shape

`hooks/guard.py`, `cited_record_path`, acts for `git commit` only. It joins the message
parts with a blank line, as git joins several `-m`, and splits them into paragraphs. In
the last paragraph only, it blanks the one path token after a `drops-lines:` key, in any
case, and only when ` -- <reason>` follows. The search then judges the rest. These stay
refused: a line in a middle paragraph, a line with no reason, a reason that names a path,
and a `gh pr create` body. The undo check reads git trailers, in the last paragraph only,
and never a PR body.

## What protects it

`hooks/test_guard.py`: twelve cases named "Drops-lines", seven of them red first over two
review rounds. `hooks/mutate_guard.py`: the mutant "excused in every paragraph", killed by
the middle-paragraph case. The exemption blanks the token after the key only when the record
pattern matches the whole token, so `deferred/a.md,deferred/b.md` stays in the searched text.

## Holes, named

Debts: `drops-dot-slash-guard-lint` (`./deferred/a.md` after the key passes the guard, and the lint refuses it), `drops-mixed-paragraph-exempt` (a last paragraph that mixes prose with the trailer is exempt in the guard), `drops-cite-forms-unchecked` (`git commit --trailer`, a `Refs:` token, `git merge -m` and `git tag -m` are never cite-checked), `drops-whole-token-no-mutant` (no mutant removes the whole-token match), `drops-reads-msg-unlike-git` (a folded trailer and a `--file=-` heredoc are read in a different order than git), `drops-stdin-message-unread` (a message from `-F -` stdin is never read).

## Named limits

- A reason that names a record path is refused, by ruling, even where the lint would accept it.
