# Notes file merges by union

## Ruling

`.gitattributes` gives `docs/debts/notes.md` git's built-in `merge=union` driver. A local `git merge`
keeps both sides' lines with no conflict. The batch runner builds the integration branch with a local
`git merge`, so it gets this.

`docs/records.md` and `docs/catalog.md` keep the default merge. They are generated tables with
sections. Union would leave duplicate or stale rows silently. The merge tool regenerates `docs/records.md`
(decision records-index-at-merge, one records index page rebuilt at merge time).

The rule takes effect only once it is on main. A lane branched before it merges needs main merged in.

Known cost: union never removes a line that one side kept. When two lanes rewrite the same note, both
versions stay. A note that one lane deletes or reverts can come back when another lane appends. A merge of a PR's
new base revived notes the PR had deleted (PR #1825, 2026-11-08). `check_silent_undo` now refuses a
revived note, matched by slug, so a reworded copy is caught. It reads the branch's own commits, so it needs no deletion on
main. It counts copies per slug: it refuses only when head holds more copies than the branch's last lowering commit left,
so a dedupe that keeps a copy passes. A note with no `- slug:` form is read by its whole line, so only the same text counts
as a copy. An octopus merge no longer hides a revival: the check keeps its findings and then reports the unread merge as UNKNOWN
(step notes-union-batch-revival). A note re-added by a non-merge commit passes. An edit in place does not keep a revived note, so a sweep edit never keeps one (lane ruling 2026-11-08 06:20 CST, upheld by the coordinator). A rebase onto main leaves no merge, so a revival there is not seen (debt silent-undo-rebase-no-merge). `lint/test_notes_union_merge.py` pins the rewrite case.

Scope: this repo only. Another repo with its own notes file adds the same line to its own
`.gitattributes`.

Unverified: GitHub's own server-side merge. The integration branch is built locally, so it does not
depend on GitHub's merge.

Why: lanes append one-line findings to `docs/debts/notes.md`, so lanes clash there. On Oct 29 batch 21
left out four reviewed lanes (PRs #811, #807, #810, #806) only for `notes.md` clashes. Batch 20 forced
seven lanes to merge main in. A census of the remerge diffs of main's merges since Oct 15 found 26
real content conflicts in `docs/debts/notes.md`, the most of any file. Next: `docs/records.md` with 11
and `docs/catalog.md` with 10.

- Risk: incident. Landed 2026-10-29.

Kind: process
Home: .gitattributes
