# One generated page lists every hook, judge, mod and skill

## The ruling

`docs/catalog.md` lists every hook, judge, mod and skill. Each row says what the entry does and which model and effort it runs on (owner ask 2026-10-13 22:25 CDT). Skills are in scope too (owner add 2026-10-13 22:26 CDT). `lint/hook_catalog.py` generates the page. Nobody keeps it by hand.

- A skill's text is the `description` in its frontmatter.
- An inline command names no script. Its summary sits in `lint/hook_catalog_inline.json` under the key: the label, ` #`, and the first 8 hex digits of the SHA-256 of the command text (owner ruling, undated).
- The label is the event, then ` matcher=<m>` and ` if=<c>` when present.
- A changed command changes its key, so `--check` fails and names the new key until a person keys the reviewed summary to the new text.
- The cell cap is in `catalog-cells-never-cut`, catalog cells are never cut.

Kind: build
Plan: docs/decisions/hook-catalog-page.md#the-ruling (all)
Home: lint/hook_catalog.py
