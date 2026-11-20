# The install after a merge can read main before the merge lands

**What.** `merge/install_from_main.sh` read main at 20:48:11Z. Pull request 3711 (branch `compaction-audit-clears`) merged at 20:48:07Z, 4 s earlier, and the install put a tree without that merge in place. Every `Audit:` spawn then crashed with `ModuleNotFoundError: layout` (guard.log) until a reinstall at 21:41Z. The cause is unmeasured.

**Where.** `merge/install_from_main.sh`, which the merge tool runs after each merge. Its test file is `merge/test_install_from_main.sh`.

**Decision.** `merge-reinstalls-from-main` (each merge reinstalls from the main checkout).

**Retire.** `merge/test_install_from_main.sh`, a case red first on the current code: a merge lands on origin, the script runs at once, and the installed tree must hold that merge. The case goes green when the install holds the merge that triggered it.
