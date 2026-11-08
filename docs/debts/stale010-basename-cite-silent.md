# A cite with no folder dodges the dead-name check

**What.** A cite such as `(guard.py missing_fn)` names a file with no folder part. `FILE_CITE` rejects it, so STALE010 never reads it and a dead name passes. STALE002 never uses `FILE_CITE`: a basename cite matches no path key there. Claude writes this form in normal work: docs/debts/notes.md holds `(guard.py impeccable_command_hit)`. <!-- ste-disable-line STALE010 -->

**Where.** lint/stale_cites.py `dead_name_cites`, and the `FILE_CITE` test it shares with STALE003.

**Decision.** record-cites-live-code (claims about code cite live code names).

**Retire.** A basename cite that matches one tracked file is read as that file, and a case in `lint/test_stale_cites.py` shows a dead basename cite gives STALE010.
