# Failed sends count as proof

**What.** The feedback Stop guard drops a send or page write whose paired `tool_result` has `is_error: true`, matched by `tool_use_id`. Still open: whether a real failed `send_message` sets that flag. If it does not, a failed send counts as proof and the guard passes. Also open: a read-back result whose id carries an `items/` prefix would false-block. Risk: likely risk, no incident. Found in review on 2026-11-02.

**Where.** `lint/_transcript.py`, `results_by_id`, pairs each `tool_result` with its `tool_use` by `tool_use_id`. `hooks/feedback_guard.py`, `Pages._uses_after`, leaves out each `tool_use` whose paired result has `is_error: true`. `Pages.proof_state` applies the proof to the uses left. `page_problem` passes `_proves(use, n, closes(use))` to `Pages.proof_state`, and `repo_problem` passes `_names_repo` to `Pages.sent`. `_proves` checks the use's name and input, never its result.

**Decision.** owner-feedback-inbox (owner feedback goes to an inbox before the turn ends).

**Retire.** The guard now rejects a send or page write whose paired `tool_result`, matched by `tool_use_id`, has `is_error: true` (`Pages._uses_after`, lane nfp-inbox-guard); a test feeds a send with an error result and asserts the guard blocks. Still open: measure on real transcripts whether a failed `send_message` sets `is_error: true`, or returns only error text. If it sets no flag, the guard must read the error text instead. Closed when that is measured and, if needed, the text read is built.
