# The ci-hygiene push snippet passes no push base

**What.** The push snippet in `skills/ci-hygiene/snippets.md` (section 20) runs the push-skip action but never reads its `base=` output or passes it to the scope step. A repo copied from the snippet has no push base, and `bin/ci-job` reads every scope term true when it gets no flags (`scope_term`), so each push runs every suite. Claude is likely to hit this, since the owner plans to point every repo at this one through `/ci-hygiene`.

**Where.** `skills/ci-hygiene/snippets.md` (section 20); `actions/push-skip/push-skip.py` (the `base=` line, line 378); `bin/ci-job` (`scope_term`).

**Decision.** `push-skip-on-proven-tree`.

**Retire.** None yet. Close when section 20 passes the base to the scope step and a test copies the snippet.

Fix: none built; this is a follow-on with the blueprint work.
