# One records index page, rebuilt at merge time

## The question

How does a reader find a decision or a debt without a search, and how does the index stay true?

## Ruling

Owner ruling, 2026-10-14 10:59 and 13:18 CDT. Each repo that keeps records has one generated index page, `docs/records.md`. It lists each decision and debt with a one-line gist. The merge tool rebuilds the page at merge time, the same way that it claims record numbers at merge. A branch never edits the page by hand. When only the page conflicts, the tool rebuilds it on the merged tree.

Kind: build
Plan: decisions/records-index-at-merge.md#ruling (all)
Home: lint/hook_catalog.py

## Why

The records grew past 300 files. A reader had to search the folders to find the ruling for a question. A hand-kept index goes stale at the first merge that forgets it, so the tool owns it.

## Holes, named

Review round 3 left these open. Lane records-heal-scope closed four. The heal stops when the generator writes no page for a conflicted page. The merge runs only the records mode of the generator (`--records-only`). A broken generator import prints one line. The heal-wait stop paths have tests. Three debts from round 3 stay open: `old-before-was-flags-history` (the history rule flags a plain description), `catalog-root-needs-skills-dir` (a settings root with hooks/ and no skills/ crashes the catalog), and `merge-by-button-stale-page` (a merge through the GitHub button leaves a stale page). Three more stay open from round 2. `silent-undo-oracle-hides-cause` (the check hides why the page failed). `page-excuse-trailer-only` (outside claude-settings, a trailer alone excuses a page drop). `index-row-drop-no-finding` (a row can drop with no finding).
