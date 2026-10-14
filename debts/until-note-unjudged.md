# The until note is checked for presence only

- **What.** The `background-end` rule accepts any non-empty `until:` text, such as `until: n/a`. No check reads whether it names a real condition.
- **Where.** `hooks/guard_stream.py`, `until_note`; `hooks/stall_watch.py`, the Stop check.
- **Decision.** `background-needs-end-note` (a background server or watcher needs an `until:` note at start).
- **Retire.** Refuse a placeholder note, or make the Stop check flag one. A test case for `until: n/a` is red before the change and green after it.
