# Notes file merges by union

## Ruling

`.gitattributes` gives `docs/debts/notes.md` git's built-in `merge=union` driver. A local `git merge`
keeps both sides' lines with no conflict. The batch runner builds the integration branch with a local
`git merge`, so it gets this.

Not union: `docs/records.md` and `docs/catalog.md`. They are generated tables with sections. Union
would leave duplicate or stale rows silently. The merge tool regenerates `docs/records.md`
(decision records-index-at-merge, one records index page rebuilt at merge time).

The rule takes effect only once it is on main. A lane branched before it merges needs main merged in.

Known cost: when two lanes rewrite or delete the same note, union keeps both versions. No incident
yet, so no check (rule building-guard-needs-incident). `lint/test_notes_union_merge.py` pins the
behaviour.

Unverified: GitHub's own server-side merge. The integration branch is built locally, so it does not
depend on GitHub's merge.

Why: lanes append one-line findings to `docs/debts/notes.md`, so lanes clash there. On Oct 29 batch 21
left out four reviewed lanes (PRs #811, #807, #810, #806) only for `notes.md` clashes. Batch 20 forced
seven lanes to merge main in. A census of the remerge diffs of main's merges since Oct 15 found 26
real content conflicts in `docs/debts/notes.md`, the most of any file. Next: `docs/records.md` with 11
and `docs/catalog.md` with 10.

- Risk: measured incident. Landed 2026-10-29.

Kind: process
Home: .gitattributes
