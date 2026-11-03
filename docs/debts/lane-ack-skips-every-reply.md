# Lane ack skips every later reply

**What.** In `last_incoming_index`, a peer message from a send's target counts as that send's ack, and the send stays counted for the turn. The skip never clears the sender's targets, so every later message from that sender is skipped, not just the first. In a lane, the parent's answer is skipped, so a second question rides on the first send. Likely in normal work. Repro: send `@parent`, the parent replies, then a new question with a `?` and no send passes.

**Where.** `lint/_transcript.py`, `last_incoming_index`. The ack branch, about :273-274, continues without clearing `sent`.

**Decision.** `questions-go-to-owner`: questions go to the owner, and each one is sent to the writer in the turn it is asked.

**Retire.** Clear the sender's target set after one skipped ack, so only the first reply from a send's target is an ack. The check: a test in `lint/test_report_guard.py`, beside `test_ln_green_ack_from_the_parent_after_a_send_keeps_the_turn`. It sends to `@parent`, the parent replies, then the session asks a new question with no send, and expects a block. The test goes red on this code first.
