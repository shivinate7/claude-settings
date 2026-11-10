# A single-quoted updatedAt in a shell command passes

**What.** The written-time check reads only double-quoted `updatedAt` values in a shell command. The incident's own step write, `d['updatedAt']='<ahead>'` in Python, passes. Claude wrote that form in normal work.

**Where.** `hooks/guard_merge.py`, `_UPDATED_AT` and the Bash branch of `_written_texts`.

**Decision.** local-time-central (sessions speak times in US Central).

**Retire.** A single-quoted `updatedAt` value ahead of the clock in a Bash command is refused, and a behind one passes. Cases in `hooks/test_guard.py`, family message-time-matches-clock, show both.
