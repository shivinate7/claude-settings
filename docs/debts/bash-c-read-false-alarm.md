# A test-runner argument inside bash -c is read as a write

**What.** A read inside `bash -c` is refused when its argument is a mutating word, such as `install` or `move`. Forms: `bash -c "pytest -k install tests/test_x.py"` and `timeout 300 bash -c "pytest -k move tests/x.py"`. Both only read the test. The shell -c branch keeps the any-position reading, so a write inside `bash -c` stays refused.

**Where.** `hooks/guard_frozen.py`, `_shell_write_hit` with `command_position`, through `_words_of` and `writes_to`. Rule 7c of `hooks/guard.py`, `builder-test-edit`, shows the refusal.

- **Decision.** `builders-cannot-edit-tests` (builders cannot edit tests; shell check).

**Retire.** Read a `bash -c` script's arguments at command position, as the rest of the shell reader does, and keep the any-position reading for a write. Closed when a red case allows both forms above, and a `bash -c` case that writes a test path stays refused.
