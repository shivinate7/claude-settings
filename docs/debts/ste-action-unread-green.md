# The ste-lint action is green on an unread input in CI

- **What.** In CI, `actions/ste-lint/run.sh` exits 0 when it could not read the changed-file list (a depth-1 clone has no `HEAD~1`: it prints `ste-lint: unknown, HEAD~1 does not exist ... Nothing was checked`, then `stale-cites: PASS`). It also zeroes the stale-cites exit when `fail` is false, though that opt-out covers findings only.
- **Where.** `actions/ste-lint/run.sh`: `FROM` is computed before `stale_cites.py` runs, so its fetch does not help; the exit is `STALE_EXIT` only; `[ "${FAIL:-true}" = "true" ] || STALE_EXIT=0` mutes an unread input.
- **Decision.** `ci-unknown-is-red` (in CI an unread input is red).
- **Retire.** Roadmap step `ste-lint-run-exit-codes` makes the action fetch the base's history first and exit non-zero on an unread input, with `fail: false` muting findings only. `actions/ste-lint/test_action.py` shows a depth-1 clone red under `CI`.
