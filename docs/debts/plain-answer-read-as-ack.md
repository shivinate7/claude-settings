# Plain reply read as ack

**What.** A target's plain reply with no "?", such as "Use a.", still reads as the ack of the send. A question that follows it passes with no send. Likely in normal work: send `@parent`, the parent replies "Use a.", and the session then asks a new question with no send.

**Where.** `lint/_transcript.py`, `last_incoming_index`. The ack branch tells an ask from an ack only by a "?".

**Decision.** `questions-go-to-owner`: questions go to the owner, and each one is sent to the writer in the turn it is asked.

**Retire.** Tell a plain reply from an ack in `last_incoming_index`. The check, not yet written: a case in `lint/test_report_guard_route.py` that sends to `@parent`, has the parent reply "Use a.", and has the lane then ask a new question with no send. It expects a block. Until then main's behaviour holds (coordinator, 2026-11-07 14:12 CST, pick A).

Fix: step:plain-answer-read-as-ack
