# The stamp check needs full history

**What.** `stamp.mjs --check` off the default branch needs `fetch-depth: 0`. A depth-1 checkout of a pull request merge commit has no parents, so the check cannot find the merge base. Unmeasured idea: use the first parent of the merge commit as the base, with `fetch-depth: 2`.

**Where.** `actions/stamp/stamp.mjs`.

**Decision.** `one-shared-record-stamp`, one shared parser, not four claim tools.

**Retire.** Revisit when a repo reports its full-history checkout is too slow. First, a fixture makes a shallow clone of a real two-parent merge commit. Closed when the check passes on it at depth 2.

## Ruling

Owner, 2026-09-28: the stamp check uses full history (`fetch-depth: 0`) for now.
