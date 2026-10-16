# A write to a frozen path in ANSI-C quotes is allowed

- **What.** Main allows `echo ok > $'<frozen path>'` at top level, and inside `bash -c`, `sh -c` and `eval`. The frozen-path check does not decode the `$'...'` quote style. Lane cap-ask-hole found it on 2026-10-15. No lane caused it.
- **Where.** The frozen-path check in `hooks/guard.py`; the quote helpers `_quoted_words` and `_unquoted`.
- **Decision.** None yet. Owner, 2026-10-15: record now, fix in a later lane.
- **Retire.** The check decodes `$'...'` words before it compares paths, with one deny case at top level and one inside each wrapper.
