# Design talk with no tool call blocks as a cannot-claim

- **What.** A reply that talks about design, in a turn with no tool call, blocks as a cannot-claim with no try. On head 2e3470ddab each of these blocks: "We can't just add a regex here.", "I can't give you a rate.", "I can't recommend the first option." and "I can't make that change without breaking the API." ("API" is an access noun, so the need keeps the claim.) A false alarm teaches the reader to scroll past the guard. The false-alarm rate is unmeasured.
- **Where.** `lint/_clause.py` `judged_object`, and `lint/report_guard.py` `_claim`, which calls it.
- **Decision.** `cant-claim-needs-probe` (a cannot-claim for an act outside the table needs one probe).
- **Retire.** Each of the four sentences passes, and "I cannot import it myself." still blocks. A test in `lint/test_report_guard_cannot.py`, red on the current code first, gives each sentence and expects no block.
