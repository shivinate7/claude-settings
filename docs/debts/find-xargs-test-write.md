# A write fed by find, xargs, a for loop or a substitution is not read

**What.** A builder can write a test by mistake through a path that a shell command supplies. These forms are allowed: `find tests | xargs sed -i`, `find tests -exec sed -i`, `for f in tests/*.py; do sed -i ... $f; done`, and `sed -i ... $(grep -rl a tests)`. The write reader does not read the paths that `find`, `xargs`, a `for` list or `$( )` supply.

**Where.** `hooks/guard_frozen.py`, `_shell_write_hit`. The builder check (rule 7c of `hooks/guard.py`, `builder-test-edit`) calls it.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (the shell check).

**Retire.** Read the paths that `find`, `xargs`, a `for` list and `$( )` feed to a write command, and judge them with the same predicate. Closed when a red case refuses each of the four forms above for a builder, and the test path in each is named.
