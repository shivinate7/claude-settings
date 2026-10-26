# The ruling-kind lint passes on zero files

- **What.** `lint/check_ruling_kind.py` checks only the committed diff against `origin/main`, so a run before the commit checks zero files and prints PASS. A record-writer runs the lint before it commits, so it is likely to read that PASS as clear. Measured 2026-10-22: a run on a clean tree at `origin/main` printed PASS (0.5 s) and named no file. Naming files on the command line checks them, committed or not.
- **Where.** `lint/check_ruling_kind.py`: `changed()` reads `git diff --name-only --diff-filter=d <base>...HEAD`, and the file loop at the end prints nothing for an empty list.
- **Decision.** `rulings-declare-kind` (each ruling declares its kind). It says the lint checks every record the pull request adds or changes, against the pull request base. It does not say what a run prints when no record is committed yet.
- **Retire.** The lint prints how many records it checked and the base it used, so a local zero is visible. CI keeps its pass on a pull request that changes no record: zero stays exit 0. Closed when a case in `lint/test_check_ruling_kind.py` shows a zero-file run prints its count.
