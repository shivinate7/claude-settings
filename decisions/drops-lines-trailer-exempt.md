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

Three review rounds, 2026-10-12. Round 1 found a second path hiding behind a comma-joined
token, and a space before the colon refused. Round 2 closed both.

- `./deferred/a.md` after the key passes the guard; the lint's exact match refuses it. The
  cost is one lint refusal, then a new commit.
- A last paragraph that mixes a prose line with the trailer is exempt in the guard. Git does
  not read such a paragraph as trailers, so the undo check refuses it. The cite then stays in
  the branch history.
- A reason that names a record path is refused, by ruling, even where the lint would accept
  it.
- Pre-existing, outside this change: `git commit --trailer`, a `Refs:deferred/a.md` token
  with no space, `git merge -m` and `git tag -m` are never cite-checked.
- No mutant removes the whole-token match; the comma and semicolon cases stand for it.
- Round 3 found three false refusals, named here under the cap; none is a wrong allow. A
  folded trailer (`Drops-lines: deferred/a.md`, then ` -- reason` on the next line) is
  refused; git unfolds it and the lint accepts it. A heredoc body given with `--file=-`
  beside `-m` parts is read last by the guard, while git orders the parts as typed. A
  message from `-F -` stdin is never read, so a prose cite there passes; pre-existing, and
  the undo lint grants no excuse there.
