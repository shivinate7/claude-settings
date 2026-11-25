# The Windows slice misses unmarked Windows-only tests

- **What.** A ready pull request runs only the Windows-marked tests. The marking audit found 45 merge cases and 85 guard cases that need a Windows mark, 130 in all. It did not judge 638 more cases. Only 51 of 1,356 guard log checks can carry the Windows flag today, from the hand list `WINDOWS_CHECKERS`. A Windows-only break in an unmarked case reaches main and first shows at the daily run. Claude hits this in normal work: any change to a Windows-only path.
- **Where.** The slice switches `GUARD_TESTS` and `MERGE_TESTS` in `hooks/test_guard.py` and `merge/test_merge.py`. The hand list `WINDOWS_CHECKERS` in `tests/guard/s40805-role-model.py`. Base jobs `checks-windows-guard` and `checks-windows-merge` in `.github/workflows/checks.yml`.
- **Decision.** `windows-prs-run-marked-tests` (a ready pull request runs only the Windows-marked tests; owner, 2026-11-24 21:19 CST).
- **Retire.** The marking build lands and every case that touches a Windows-only branch carries its mark. A case in `lint/test_windows_split.py` fails on any Windows-only branch that no mark covers, and passes on the marked tree.
- **Reported.** 2026-11-24 23:06 CST (lane `windows-prs-run-marked-tests`).
