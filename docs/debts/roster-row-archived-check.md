# A roster row can name an archived session, and no refusal names the roster

**What.** Three gaps, one queued step. (a) Nothing flags a roster row that names an archived session. (b) An inactive-target refusal does not name the roster. (c) The page writer in `.claude/layout-extras.json` (key `page-writer`) still names archived session `session_013NEJKzyLYRTQKeLpis8JKJ`. The page-writer fallback in `lint/report_guard.py` reads that key when no page read names a writer. Queued step `roster-row-archived-check`, queued in chat on Nov 18-19.

**Where.** (a) `hooks/own_session.py`, `roster_rows` and `roster_session_lines`: the SessionStart roster block prints each row and does not read its archive status. (b) `hooks/guard_merge.py`, `target_roster_hit`: the send refusal that reads the roster. (c) `.claude/layout-extras.json`, key `page-writer`.

**Decision.** `brief-ids-in-roster` (the roster is the one source of who holds a standing session, and a brief names a slug or a role, never a session id). `session-tiers` (the Standing sessions list is the roster, and the page writer is named in the same tiers).

**Retire.** `hooks/test_session_start.py` holds a case, red first on the current code, where a roster row that names an archived session is flagged in the SessionStart block. `hooks/test_guard.py` holds a case, red first, where a send to an inactive target is refused and the refusal names the roster. `lint/test_report_guard_page_writer.py` holds a case, red first, where a page-writer key that names an archived session is flagged.
