# Duo-fold suite fails 2 of 38 inside a Claude session

**What.** Inside a Claude session, `lint/test_duo_fold.sh` fails 2 of its 38 cases. Measured 2026-11-24: 36 passed, 2 failed, at its lines 307 and 318 ("the clone was not the first git call"). Each case removes its case folder with `rm -rf` (line 89). The rm shim refuses that removal in a session, and the folder stays. The folder holds the case's temp HOME (line 95). Claude meets it on any run of this suite in a session.

**Where.** `lint/test_duo_fold.sh`, the case folder and its temp HOME (lines 89 and 95), and `hooks/guard_rm_var.py`, `_rm_target_bad` (line 159), which refuses the removal.

**Decision.** `none`.

**Retire.** `lint/test_duo_fold.sh`, which passes 38 of 38 inside a Claude session. The debt closes when it does.
