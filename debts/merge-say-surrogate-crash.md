# The merge tool can crash printing a non-UTF-8 name

- **What.** The merge tool prints ALLOWED notes and an excused UNKNOWN to stdout with a plain print. A non-UTF-8 file name in that text raises an encode error on a strict stdout. Confirm then fails closed; preview shows a traceback. No finding passes.
- **Where.** `say()` in `merge/merge.py`, called from `undo_check`.
- **Decision.** `silent-undo-check-design` (how the check finds a merge that drops lines).
- **Retire.** The merge tool's `say()` encodes with backslash escapes, as the scanner's `say()` does. A case prints a surrogate name on a strict cp1252 stdout.
