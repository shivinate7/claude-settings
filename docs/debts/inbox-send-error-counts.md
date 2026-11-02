# Failed sends count as proof

**What.** The feedback Stop guard counts a send as proof, even when the send failed. A send to a dead or wrong session id returns an error. The guard reads only the send's `tool_use` block. It never reads the `tool_result` that answers it. Scenario: the send fails, the turn ends, and the guard passes. This holds for page items. It also holds for repo items. Repo items exist only on branch `one-inbox-per-repo`, the lane that adds them. Measured: neither `hooks/feedback_guard.py` nor `lint/_transcript.py` reads `is_error`, on main or on that branch. Unmeasured: whether a failed `send_message` sets `is_error: true`, or returns only error text. Risk: likely risk, no incident. Found in review on 2026-11-02.

**Where.** `lint/_transcript.py`, `tool_uses`, the transcript reader. It yields `tool_use` blocks only, so no result is paired with a send. `hooks/feedback_guard.py`, `_proves`, the send matcher. It checks the send's name and message text, not its result. `page_problem` passes `lambda use: _proves(use, n)` to `Pages.sent`, which applies it to each `tool_use` after the anchor. On branch `one-inbox-per-repo`, `repo_problem` does the same with `_names_repo`.

**Decision.** owner-feedback-inbox (owner feedback goes to an inbox before the turn ends).

**Retire.** A send counts only when its matching `tool_result`, the one with the same `tool_use_id`, is not an error. The fix goes in `tool_uses` or in `sent`, so both kinds change. Page items change too, since `Pages.sent` uses the same matcher. If the unmeasured point above shows no error flag, the fix must read the error text instead. Measure that first. Closed when a test feeds a send with an error result and asserts that the guard blocks.
