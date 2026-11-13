# A python write to a path built at run time is not read, so it can reach another checkout

**What.** A python script can write into another checkout by mistake through a path the scan cannot resolve: an f-string, a `+` concatenation, an unbound variable, `os.open`, `subprocess` or a delete. The scan reads only literal paths, so the write passes. The harm: a file lands in, or vanishes from, a checkout the session does not own.

**Where.** `hooks/guard_frozen.py`, `_py_written` (read through `interpreter_write_hit`).

**Decision.** `an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop (`other-checkout`, the ceiling).

**Retire.** When `hooks/test_guard.py` holds a red case that refuses each form into another checkout, the debt is closed. To retire it, resolve a path built from a string join, an f-string or a bound name, and read `os.open`, `subprocess` and deletes as writes.
