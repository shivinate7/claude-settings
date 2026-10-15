# The silent-write check does not read a bash -c script

- **What.** A silent git write inside `bash -c '...'` is allowed. The silent-write check reads only the outer command. The test pin was cut in lane cut-tests-guard. Debt `guard-shell-wrap-discard-unread` names the same wrapper gap for another rule.
- **Where.** The silent-write rule in `hooks/guard.py`.
- **Decision.** `test-strategy-reset` (a hole pin becomes a debt).
- **Retire.** The check reads the script of `bash -c` and `sh -c`, with one deny case.
