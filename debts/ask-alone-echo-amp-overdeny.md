# A quoted & in echo text counts as a step

- **What.** `UNSAFE_TEXT` marks `<`, `>` and `&` in a segment, quoted or not. A harmless tail such as `&& echo "R&D"` then counts as a step, so a chain with an ask step denies. Measured: that tail counts 0 harmless. Safe direction: an over-deny, no hole.
- **Where.** `UNSAFE_TEXT` and `harmless_steps` in `hooks/guard.py`.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** Quoted `<`, `>` and `&` pass the text check, while `$(` and backticks still count. A row in `hooks/test_guard.py` shows `<ask> && echo "R&D"` asks alone, and an unquoted `&` in the same tail still denies.
