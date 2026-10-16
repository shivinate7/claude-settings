# A trailing newline or ; stops the harmless tail count

- **What.** An empty last segment ends the tail loop in `harmless_steps`, so a harmless tail before it is not counted. Measured: `<cmd> && echo done` counts 1 harmless. The same text with a trailing newline or `;` counts 0, so a chain with an ask step denies. Safe direction: an over-deny.
- **Where.** `harmless_steps` and its `plain` helper in `hooks/guard.py`. `plain` returns None for an empty segment.
- **Decision.** `ask-steps-run-alone`, a step that asks the owner runs alone.
- **Retire.** The tail count skips empty segments, as `count_steps` already does. A row in `hooks/test_guard.py` shows an ask step with `&& echo done` and a trailing newline asks alone.
