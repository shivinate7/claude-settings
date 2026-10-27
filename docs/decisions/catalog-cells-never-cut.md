# Catalog cells are never cut

## Ruling

The cell cap in `docs/catalog.md` sits above the longest cell, so no cell is cut. Test e13, no real cell is
cut, goes red on any cut cell, so cut text never reaches main. A cell that grows past the cap, such as a
`skills/impeccable` description that impeccable-sync pulls from upstream, needs a shorter source description
or a higher cap.

Kind: build
Plan: docs/decisions/catalog-cells-never-cut.md#ruling (all)
Home: lint/hook_catalog.py
