# The pick guard reads an archived page writer, so each owner question raises a false alarm

**What.** The pick guard finds the page writer in the `page-writer` key of `.claude/layout-extras.json` when no `meta/page` read names one. That key names an archived session. A send to it returns `session_inactive` (reported 2026-11-19, not reproduced in this tree). So the guard raises a false alarm on every owner question. Debt `roster-row-archived-check` (the roster-row debt) covers the stale key, its part (c), which has the same key and reader. Its Retire flags the key and does not clear this refusal. This debt holds the close of the refusal.

**Where.** `lint/report_guard.py`, `question_problem` and `page_writer_id`, which read the key. `.claude/layout-extras.json`, key `page-writer`. The key's name is `PAGE_WRITER_KEY` in `lint/layout.py`.

**Decision.** `session-tiers` (the standing sessions, the page writer among them) and `brief-ids-in-roster` (a brief names a slug or a role, never a session id).

**Retire.** `lint/test_report_guard_page_writer.py`, a case red first on the current code: a pick turn whose page-writer key names an archived session is not refused by the pick guard.
