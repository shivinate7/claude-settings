# A commit's Drops-lines trailer may name a record path

## The ruling

Owner, 2026-10-12: the `Drops-lines: <record path> -- <reason>` trailer is the one place a record path is allowed in a commit message. Everything else on that line, and every other line, is still judged by the cite-by-id rule (`git-cite-by-id`; guard rule `cite-by-id`).

- `cited_record_path` in `hooks/guard.py` acts for `git commit` only. It joins the message parts with a blank line, as git joins several `-m`, and splits them into paragraphs.
- In the last paragraph only, it blanks the one path token after a `drops-lines:` key, in any case, and only when ` -- <reason>` follows. The record pattern must match the whole token, so `deferred/a.md,deferred/b.md` stays in the searched text.
- These stay refused: a line in a middle paragraph, a line with no reason, a reason that names a path (by ruling, even where the lint would accept it), and a `gh pr create` body.

Why: the silent-undo check (`silent-undo-check-design`) requires the trailer when a PR deletes record lines. It reads git trailers in the last paragraph only, never a PR body. The guard refused the trailer itself.

Protected by the twelve "Drops-lines" cases in `hooks/test_guard.py` and the mutant "excused in every paragraph" in `hooks/mutate_guard.py`.

## Holes, named

Debts: `drops-dot-slash-guard-lint` (`./deferred/a.md` after the key passes the guard, and the lint refuses it), `drops-mixed-paragraph-exempt` (a last paragraph that mixes prose with the trailer is exempt in the guard), `drops-cite-forms-unchecked` (`git commit --trailer`, a `Refs:` token, `git merge -m` and `git tag -m` are never cite-checked), `drops-whole-token-no-mutant` (no mutant removes the whole-token match), `drops-reads-msg-unlike-git` (a folded trailer and a `--file=-` heredoc are read in a different order than git), `drops-stdin-message-unread` (a message from `-F -` stdin is never read).

Kind: process
Home: hooks/guard.py
