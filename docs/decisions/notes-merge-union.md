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
revived note, matched by slug, so a reworded copy is caught. It counts copies per slug: it refuses only when head
holds more copies than the branch's last lowering commit left, so a dedupe that keeps a copy passes. It skips a note
with no `- slug:` form. A note re-added by a non-merge commit passes. An edit in place does not keep a revived note, so a sweep edit never keeps one (lane ruling 2026-11-08 06:20 CST, upheld by the coordinator). `lint/test_notes_union_merge.py` pins the rewrite case.

Check: `lint/check_record_slugs.py` fails a lane only when the lane's diff raises a slug's row count above
its count at the merge base of origin/main and HEAD. The slug must then have two or more rows. Slugs compare
without case. Duplicates already on main do not fail a lane. With file names given, or when git cannot read
the diff, any duplicate in the file fails. `--list` prints every duplicate in the checkout's notes file,
main's included, and exits 0 (1 only when the layout cannot be read). It names slugs, not lanes. The
batch runner calls it under ci-hygiene step 8 (Batch lanes).
A rewrite that union keeps twice goes red when the lane raises the count. A deleted row that union restores has one slug, so this check passes it; `check_silent_undo` (above) is
the check for a revived row. Step `notes-union-batch-revival` (the batch revival case, filed with triage)
tracks whether a batch integration merge is caught.
Incidents: main held 9 duplicate slugs at commit e2703c611 (PR #1824). Merging PR #1449 into batch 64
took the integration branch to 13 duplicate slugs. PR #1824 brought main back to 9. PR #1920 was dropped
from batch 65 for a duplicate slug (runner 8's message, 10:35 CST, 2026-11-08). Only a fix check caught
them (roadmap step notes-slug-unique, Nov 8).

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
