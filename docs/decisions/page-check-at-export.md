# A waiting item's picture is checked at export and before a republish

## The ruling

Owner ruling, item 298 (14:17 CST Nov 6 2026): build both the check at export and the `--check` mode. The page's own item checks run before the page goes out, not only in the owner's browser.

- Why: the write-time guard (decision `page-item-design`) fails open, so a bad item can still reach the page. Item 292 did, Nov 6 2026, with "The picture of option A shows nothing the focus names." On that day, `check_designs.mjs` refused it against the page copy on the record branch.
- `skills/waiting-page/page_check.py` is the one home that starts the checker (`run_check_designs`). The guard and `export_page.py` both call it. The checker runs the page's own `pictureProblem`, so this repo holds no copy of that check.
- Export (`export_page.py --page`, and the waiting-page entry of `--all`) always writes the copy first. Export is the backup path, so a bad item never holds the copy back (rule `verification-recovery-independent-of-state`). Then it prints `held item <n>: <the page's sentence>` once per bad item, and exits 4. The writer does not republish while an item is held.
- `export_page.py --check --fetched DIR --page FILE` runs the same checks and writes nothing. Exit 0 prints `checks pass`. Exit 4 prints the held lines. Exit 3 prints `checks unknown: <why>`. The writer runs it before every republish (skill `waiting-page`).
- Scope: open items that carry a picture (`question_form.design_writes`). Answered items are skipped by `page_check.answered_on_page`. That function copies page.html's `isAnswered` and `waitsOf`. The checker's stub database holds no answers, so the page cannot be asked. Known limit: this copy can drift from the page.
- Unknown at export (no node, Playwright or Chromium): the run prints one `checks unknown:` line and keeps its exit code.
- Cost: one node start and one Chromium start per pictured open item, at each export and each `--check`. The budget is 100 s per run. The run adds no timer and no log.

Kind: process
Home: rule:questions-go-to-owner
