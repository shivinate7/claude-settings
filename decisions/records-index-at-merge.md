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

Review round 3 left these open. Debts: `records-heal-keeps-markers` (a heal can commit conflict markers), `records-gen-runs-catalog` (the merge runs the whole catalog generator), `merge-catalog-import-traceback` (a broken catalog module gives a traceback), `records-heal-wait-untested` (the heal-wait stop paths have no test), `old-before-was-flags-history` (the history rule flags a plain description). Lane records-heal-scope takes the first four.
