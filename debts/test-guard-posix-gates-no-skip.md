# test_guard.py gates drop cases on POSIX with no SKIP row

- **What.** Two case blocks in the guard test suite run only on one platform: Windows (`os.name == "nt"`) and macOS (`sys.platform == "darwin"`). Elsewhere the gate drops them and prints no SKIP row. A reader sees no sign that cases did not run.
- **Where.** The two platform gates in `hooks/test_guard.py`, near lines 2847 and 3167.
- **Decision.** `test-strategy-reset` (a skipped test reports SKIP with a count, never PASS).
- **Retire.** Each gate appends a SKIP row with a reason, and the summary line counts the skips. A test shows a dropped case as SKIP on POSIX.
