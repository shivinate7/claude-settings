# Waiting page sort and repo sub-groups: review record

Lane waiting-page-sorting. Mockup `docs/design/tier-sort.html`, notes `tier-sort-notes.md`.
Written by the lane from the reviewers' reports; the reviewers' roles cannot write in the repo.

## Design review (design reviewer, opus)

- Round 1, head 830719cf7: PARTIAL. Every drawn state matched the mockup at 390, 800 and 1280, light and dark (48 runs).
  Defect 1: repo heads drew before `meta/page`, then vanished and Whenever re-sorted. Defect 2: first rail run had a top gap at 1280.
- Round 2, head a7c9f0400: FAIL on one state. Both round 1 defects fixed. New: a `meta` that never arrives left "Loading…" forever; the loading line had no live region.
- Round 3, head bbca68d40: PASS at all six size and theme combinations. A 10 s timer settles a silent `meta`; the loading line is `role=status`, `#list` is `aria-busy` while held; a late `meta` moves no card; lowest contrast 5.9:1.
- Open, filed as notes in `docs/debts/notes.md`: repo-less items head "this repo" after a failed or timed-out `meta` (reads as a second "this repo" beside the named repo); a hint at about 3 s for the 10 s wait. Real store timing is unmeasured.
- Not run: axe CI check, forced colors, 200% zoom.

## Code review (reviewer)

- Round 1, head 830719cf7 (haiku): FAIL. The new guard refusal cited no decision; card count read live `stops` while the sort read the frozen key; SKILL.md claimed a stronger refusal than the guard makes.
- Round 2, head a7c9f0400 (sonnet): PASS. Debt: no time limit on the loading line (fixed in the next step); rail-hidden test gap (fixed).
- Round 3, head bbca68d40 (sonnet): PASS. Net safety value zero: the rule closes no hole against main and opens none that counts. Merge-ready.
- Open, filed as notes: a `meta` error after a good `meta` flips the split (`meta-error-after-meta-flips-split`); the `holds`-reword gap (debt `stops-holds-reword-gap`).
