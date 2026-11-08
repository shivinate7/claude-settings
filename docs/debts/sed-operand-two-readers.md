# sed operands have two readers

**What.** `_sed_script_words` (hooks/guard_frozen.py) reads sed's `-e`, `-f`, `--` and first-word operands, and `_pattern_words` (hooks/guard_env.py) reads the same operands. Two homes for one capability, with no stated reason.

**Where.** hooks/guard_frozen.py `_sed_script_words`; hooks/guard_env.py `_pattern_words`.

**Decision.** none.

**Retire.** One reader, called from both places. Shown by `hooks/test_guard.py`.
