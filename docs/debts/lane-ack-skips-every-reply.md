# Lane ack skips every reply

**What.** In `last_incoming_index`, a send's first reply from its target is its ack, so a new question in that reply passes with no send. Likely in normal work: send `@parent`, the parent replies once, and the reply asks a new question with no send; a send to the writer does the same.

**Where.** `lint/_transcript.py`, `last_incoming_index`. The ack branch cannot tell an ack from an answer.

**Decision.** `questions-go-to-owner`: questions go to the owner, and each one is sent to the writer in the turn it is asked.

**Retire.** Tell an ack from an answer in `last_incoming_index`. The check, not yet written: a case in `lint/test_report_guard_route.py` that sends to `@parent`, has the parent reply once, and has that reply ask a new question with no send. It expects a block. Until then main's behaviour holds (orchestrator pick, 2026-11-03 18:29 CST, process-only).
