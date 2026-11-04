# Lane ack skips every reply

**What.** In `last_incoming_index`, the first reply from a send's target is read as that send's ack, and the send stays counted for the turn. A reply that holds a new question is read the same way. Likely in normal work. Repro: send `@parent`, the parent replies once, then a new question with a `?` and no send passes. The same holds for a send to the writer. This branch fixed the "every later message" part: the ack now uses up the sender's targets, so a second reply starts a turn.

**Where.** `lint/_transcript.py`, `last_incoming_index`. The ack branch cannot tell an ack from an answer.

**Decision.** `questions-go-to-owner`: questions go to the owner, and each one is sent to the writer in the turn it is asked.

**Retire.** Find a way to tell an ack from an answer. Until then main's behaviour holds (orchestrator pick, 2026-11-03 18:29 CST, process-only).
