# One records index page, rebuilt at merge time

## Ruling

Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and
debt with a one-line gist. The merge tool rebuilds the page at merge time, the same way that it claims
record numbers at merge. A branch never edits the page by hand. When only the page conflicts, the tool
rebuilds it on the merged tree.

The page is rebuilt only at merge. A lane never commits a change to `docs/records.md`, not even one made
by `lint/hook_catalog.py`. PR CI already accepts a stale page (`lint/hook_catalog.py --check` waives it
on a PR run). The guard `records-page` refuses a lane commit whose staged `docs/records.md` differs from
the page on the lane's base. A merge of the base into the lane brings the base's page, so it is allowed.

Reason: a hand-kept index goes stale at the first merge that forgets it, so the tool owns it. Lanes that
each rebuilt the page conflicted on it in three batches.

Kind: build
Plan: decisions/records-index-at-merge.md#ruling (all)
Home: lint/hook_catalog.py

## Holes, named

The heal stops when the generator writes no page for a conflicted page. The merge runs only the records
mode of the generator (`--records-only`). A broken generator import prints one line. The heal-wait stop
paths have tests. `RECORDS_HEADER` in `hooks/guard_merge.py` copies the first line of `RECORDS_INTRO` in
`lint/hook_catalog.py`, and a pin test compares them.

Debts: `old-before-was-flags-history`, `merge-by-button-stale-page`, `silent-undo-oracle-hides-cause`,
`page-excuse-trailer-only`, `index-row-drop-no-finding`.

Debts on the guard `records-page`:

- `records-page-reader-gaps`: the guard reads only the paths of `git commit -i` or `--include`. It does not read `git rebase`, `git cherry-pick`, `git am` or `git revert`. It does not read a `sh -c`, `bash -c` or `cmd /c` script. `python -m lint.hook_catalog` does not count as a generator run.
- `records-page-first-adoption`: a base with no page lets any page commit pass, by design.
- `records-page-gen-false-alarm`: a generator run, then a commit that holds the page in the same call, is denied with no compare of the page.
- `records-page-colon-spec-alarm`: `git add -A ':!docs/records.md'` likely counts as an add that reaches the page (read from code, unrun).
- `records-page-handwritten-header`: a hand-written page that opens with `# Records index` reads as generated.
