# The page-form check misses a writer stored as a label

**What.** `PageState.is_writer` in `hooks/feedback_guard.py` compares the page writer with `== session_id`. The page stores `Triage (session_...)`, so a cloud writer reads as not the writer and `page_form_problem` passes silently. It also ignores the remote session id. Step `waiting-export-miss-cloud` fixed the same match in the export check with `_writer_names`. Cost unmeasured; it has hit no one yet.

**Where.** `hooks/feedback_guard.py`, `PageState.is_writer` (about line 715) and its caller in the page-form check (about line 952).

**Decision.** `waiting-page-one-store`.

**Retire.** Reuse `_writer_names` in `is_writer`, red first with a label writer and a remote id.
