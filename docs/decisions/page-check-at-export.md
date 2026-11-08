# A waiting item's picture is checked at export and before a republish

## The ruling

Owner ruling, item 298 (14:17 CST Nov 6 2026): build both the check at export and the `--check` mode. The page's own item checks run before the page goes out, not only in the owner's browser.

- Why: the write-time guard (decision `page-item-design`) fails open, so a bad item can still reach the page. Item 292 did, Nov 6 2026, with "The picture of option A shows nothing the focus names." On that day, `check_designs.mjs` refused it against the page copy on the record branch.
- `skills/waiting-page/page_check.py` is the one home that starts the checker (`run_check_designs`). The guard and `export_page.py` both call it. The checker runs the page's own `pictureProblem`, so this repo holds no copy of that check.
- Export (`export_page.py --page`, and the waiting-page entry of `--all`) always writes the copy first. Export is the backup path, so a bad item never holds the copy back (rule `verification-recovery-independent-of-state`). Then it prints `held item <n>: <the page's sentence>` once per bad item, and exits 4. The writer does not republish while an item is held.
- `export_page.py --check --fetched DIR --page FILE` runs the same checks and writes nothing. Exit 0 prints `checks pass`. Exit 4 prints the held lines. Exit 3 prints `checks unknown: <why>`. The writer runs it before every republish, on the file about to be published (the `stale_pages.py --write` output), never the live page (skill `waiting-page`).
- Owner ruling, item 276 a ("one rule": a check that cannot read its input fails, never passes): the writer holds the republish on any `--check` exit but 0. Exit 3 (`checks unknown`) and a missing page file hold it, as a held item does.
- Scope: items that carry a picture (`question_form.design_writes`, which drops closed items and rulings). The exporter fetches the answers and gives them to the checker with `--answers FILE` (the answers collection as `{doc id: doc}`). The checker loads them into its stub database and skips an item when the page's own `isAnswered` says it is answered. This repo holds no copy of that test. The guard passes no answers, so the checker skips no item and calls no `isAnswered`: its verdicts at write are the same as before this change.
- Unknown at export (no node, Playwright or Chromium, or a pictured item and no page file): the run prints one `checks unknown:` line (`checks unknown: no page file` for no page) and keeps its exit code. Under `--all`, a held item is exit 4 only when no artifact was refused (1), unknown (2) or crashed (3); the worse code wins.
- Cost: one node start and one Chromium start per pictured item, answered or not, at each export and each `--check`. Each run has the per-run cap (25 s). No time budget spans a whole run, because no hook timeout applies to export or `--check`. The run adds no timer and no log.

Kind: process
Home: rule:questions-go-to-owner
