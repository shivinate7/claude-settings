# A catcher with an import fallback can read CAUGHT after a failed install

- **What.** A defect claimed only by a part that installed runs even when its catcher imports a package of a failed part. If the catcher passes its clean run without that package (an optional-import fallback) and the fallback asserts on the plant, it reads CAUGHT where it would read MISS with the package. No live entry reaches it today (`.github/known-defects.json`).
- **Where.** `hooks/mutate_shared.py` `run_known_defects` (the failed-install check before `_known_defect`) and `_needed_parts` (routing by regex only, not by what the catcher imports).
- **Decision.** mutation-ci-report-and-replay (a defect needs a part's install by its `code` and `tests` regexes).
- **Retire.** Route by what the catcher loads, or make a fallback read UNKNOWN, with a case that goes red on the old code. `hooks/test_mutate_ci.py` pins the same-part fallback today; the fix adds the cross-part case and the debt closes when the file is green.
