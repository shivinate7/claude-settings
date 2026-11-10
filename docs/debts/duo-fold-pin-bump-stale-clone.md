# A pin bump leaves a stale hinge clone that duo-fold refuses on

**What.** `duo_fold_fetch_hinge` skips the clone when `$work/hinge/.git` exists, then runs `git checkout` of the pinned sha. After the pin in `bin/duo-fold` moves, a machine whose `DUO_FOLD_WORK` clone predates the move has no object for the new sha, the checkout fails, and every fold refuses with "could not fetch hinge". The tool keeps the behaviour of home's `scripts/duo-fold.sh` at e7f2b5d6 (port rule), so the port did not fix it.

**Where.** `bin/duo-fold`, `duo_fold_fetch_hinge`.

**Decision.** duo-fold-tool.

**Retire.** `duo_fold_fetch_hinge` fetches the pinned sha when its checkout fails. A case in `lint/test_duo_fold.sh` starts from an existing clone that lacks the new sha and shows the fold passes.
