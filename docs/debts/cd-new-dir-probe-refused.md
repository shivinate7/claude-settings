# A builder probe that cds into a folder it creates in the same command is refused

**What.** A builder that runs `P=/tmp/x && mkdir -p "$P/tests" && cd "$P" && : > tests/a_test.mjs` from a worktree is refused when `$P` does not exist yet. The `cd` target does not exist at hook time, so the write is judged against the worktree. The write lands in no repository, so this is a false alarm.

**Where.** `hooks/guard_core.py`, `dir_before_segment`, which trusts no `cd` into a missing folder. The builder check (rule 7c of `hooks/guard.py`, `builder-test-edit`) reads it through `_shell_write_hit`.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (false alarms pinned).

**Retire.** Trust a `cd` into a missing folder only where a failed `cd` stops the write (an `&&` chain), with the folder outside every checkout. Closed when the pinned case "builder-test (shell-cd)" for a folder the same call creates turns to allow in `hooks/test_guard.py`, and the `;` and missing-folder cases still refuse.
