# A new triage session does not rewrite its roster row at start

**What.** A new triage session does not rewrite its own roster row when it starts. The row keeps the old triage session's id. A session holds the standing merge role only when its id matches a standing row, so the new triage session's id misses the row. Queued step `triage-start-rewrites-roster`, queued in chat on Nov 18-19.

**Where.** `hooks/session_start.sh`, the standing merge role block, and `hooks/own_session.py`, `sync_standing_merge_role`. Both read the Standing sessions rows of the roadmap record. Neither writes a row. Only the triage session writes that branch (`RECORD_WRITER_TIER` in `hooks/guard_merge.py`).

**Decision.** `session-tiers` (the Standing sessions list is the one roster, and the triage session is the one writer of the record branch).

**Retire.** `hooks/test_session_start.py` holds a case, red first on the current code, where a new triage session's start rewrites its roster row to its own id on the record branch.
