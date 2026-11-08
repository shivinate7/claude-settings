# Pointer-head reads a cd to a variable path as the cwd

**What.** The pointer-head rule judges each segment in the folder `dir_before_segment` gives. A cd target that holds a variable gives None, and the rule then reads the cwd. So `cd "$HOME/claude-settings" && git switch x`, run from another folder, moves the pointer checkout's HEAD with no refusal. Main expanded the variable and refused.

**Where.** `hooks/guard.py` rule 1b (pointer-head), with `hooks/guard_core.py` `dir_before_segment`.

**Decision.** recovery-independent-of-state (the pointer checkout's HEAD stays main).

**Retire.** Rule 1b also refuses when the whole-command `head_root` reads the pointer, or expands the variable as `_absolute` does. A pointer-head case for the `"$HOME/..."` and `"$CLAUDE_PROJECT_DIR"` forms in `hooks/test_guard.py` goes red first.
