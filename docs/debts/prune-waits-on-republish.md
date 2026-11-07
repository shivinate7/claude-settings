# A closed item's mockup stays until the page is behind

**What.** `stale_pages.py --write --items` drops the mockups of closed items, but the writer republishes only a page that is `behind`. Closing an item republishes nothing, and the batch "Update a repo's pages" passes no `--items`. So on a page that stays `current`, a closed item's mockup stays on the page and in its 16 MB budget. Step: page-design-prune (drop the mockups of closed items, a roadmap step). Review round 1 found it.

**Where.** `skills/waiting-page/SKILL.md`, "Keep the page on main's code" step 4 and "Update a repo's pages", and `skills/waiting-page/stale_pages.py` single-page `--write`.

**Decision.** none.

**Retire.** Prune also when a page is `current` but holds the mockup of a closed item. Either the writer republishes it, or the batch passes `--items`. The check is a case in `skills/waiting-page/test_stale_pages.py`: a `current` page that holds a closed item's mockup comes out without it, and the path the writer runs says to republish it.
