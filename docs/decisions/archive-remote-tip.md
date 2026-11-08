# A remote delete or an archive push keeps the old remote tip

## The ruling

A push that would drop the remote tip of a branch, with no other copy, is refused. Rule id
`archive-remote-tip`. The tip is read from the local remote-tracking ref, never fetched.

| Push | Outcome |
|---|---|
| A remote delete of X (`--delete`, `-d`, `:X`), X's tip on the default base or on an archive ref | allow |
| The same delete, X's tip on neither | deny |
| The same delete, X has no remote-tracking ref | allow (no tip to lose; the incident needed a tracking tip) |
| The same delete, git cannot answer | ask (unknown tip) |
| An archive push `<src>:archive/<name>` (or `:refs/heads/archive/<name>`), the tip of `<name>` an ancestor of `<src>`, of the default base, or of an archive ref | allow |
| The same archive push, the tip in none of them | deny |
| The same archive push, `<name>` has no remote-tracking ref | allow |
| The same archive push, `<src>` does not resolve, or git cannot answer | ask (unknown) |

- An archive ref is any `refs/remotes/<remote>/archive/*`. A ref such as `old-archive/x` does not count.
- A forced push keeps the `force-push` refusal; this rule runs after it. A delete of the record branch keeps
  `roadmap-one-writer`; this rule runs after it.
- A delete of `archive/<name>` does not count its own `refs/remotes/<remote>/archive/<name>` as a holder:
  that ref goes with the delete. It passes only when the tip is on the default base or in another archive ref.
- A dry run writes nothing and passes.
- A push that names no remote is not read: with no refspec there is no name to judge.
- The deny names `<branch>` and `<remote>` only: never a real name, never a forced push.

Cost: no new process or file. A push that is no delete and no archive push reads nothing. A delete or an
archive push reads each of these once, with no `git config`:

- one `rev-parse` for the tracking tip, and one for the source of an archive push.

Then it reads until one arm passes:

- one `merge-base --is-ancestor` for the source;
- one `symbolic-ref`, one to three `rev-parse`, and one `merge-base` for the default base;
- one `for-each-ref --contains` for every archive ref at once.

## The mistake

A lane amends a branch, then pushes it to `archive/<branch>`. Origin's old tip is in no archive branch. A
later remote delete of the branch loses that commit.

Risk: incident (lane amend then archive push, 2026-11-08).

Kind: process
Home: hooks/guard_push_delete.py
