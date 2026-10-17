# One records index page, rebuilt at merge time

## The question

How does a reader find a decision or a debt without a search, and how does the index stay true?

## Ruling

Owner ruling, 2026-10-14 10:59 and 13:18 CDT. Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and debt with a one-line gist. The merge tool rebuilds the page at merge time, the same way that it claims record numbers at merge. A branch never edits the page by hand. When only the page conflicts, the tool rebuilds it on the merged tree.

Owner ruling, 2026-10-16 10:28 CDT: "Also add a guard". The page is rebuilt only at merge. A lane never commits a change to `docs/records.md`, not even one made by `lint/hook_catalog.py`. PR CI already accepts a stale page (`lint/hook_catalog.py --check` waives it on a PR run). The guard refuses a lane commit whose staged `docs/records.md` differs from the page on the lane's base. A merge of the base into the lane brings the base's page, so it is allowed. Incident: on 2026-10-16 each lane rebuilt the page, and three batches conflicted on it.

Kind: build
Plan: decisions/records-index-at-merge.md#ruling (all)
Home: lint/hook_catalog.py

## Why

The records grew past 300 files. A reader had to search the folders to find the ruling for a question. A hand-kept index goes stale at the first merge that forgets it, so the tool owns it.

## Holes, named

Review round 3 left these open. Lane records-heal-scope closed four. The heal stops when the generator writes no page for a conflicted page. The merge runs only the records mode of the generator (`--records-only`). A broken generator import prints one line. The heal-wait stop paths have tests. Two debts from round 3 stay open: `old-before-was-flags-history` (the history rule flags a plain description) and `merge-by-button-stale-page` (a merge through the GitHub button leaves a stale page). Three more stay open from round 2. `silent-undo-oracle-hides-cause` (the check hides why the page failed). `page-excuse-trailer-only` (outside claude-settings, a standalone check excuses a page drop by trailer alone). `index-row-drop-no-finding` (a row can drop with no finding).

The guard `records-page` passed review round 3 with a positive net value, so it merges on green. Each open finding is a limit below. Each one also has a debt in the debt store.

- Hole: `git commit -i` or `--include` with paths reads only the paths. A page staged earlier is missed. Debt: `records-page-reader-gaps`, the commit shapes the guard does not read.
- Hole: `git rebase`, `git cherry-pick`, `git am` and `git revert` are not read. Same debt.
- Hole: a `sh -c`, `bash -c` or `cmd /c` script is not read. `python -m lint.hook_catalog` does not count as a generator run. Same debt.
- Hole, by design: a base with no page lets any page commit pass, for a first adoption. Debt: `records-page-first-adoption`, the base with no page.
- False alarm: a generator run, then a commit that holds the page in the same call, is denied with no compare of the page. The deny holds when the page is unchanged. `--root <other>`, `-h` and the abbreviation `--che` count as a run. Debt: `records-page-gen-false-alarm`, the generator word.
- Likely false alarm, from reading the code, unrun: `git add -A ':!docs/records.md'` counts as an add that reaches the page, because `_names_page` returns True for each `:` pathspec. Debt: `records-page-colon-spec-alarm`, the exclude pathspec.
- Hole: a hand-written page that opens with `# Records index` reads as generated. Debt: `records-page-handwritten-header`, the header test.
- Closed: `RECORDS_HEADER` in `hooks/guard_merge.py` copies the first line of `RECORDS_INTRO` in `lint/hook_catalog.py`. A pin test compares them.
