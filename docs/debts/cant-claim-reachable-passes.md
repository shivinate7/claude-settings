# A cannot-claim about a whether clause passes with no try

- **What.** "I can't check whether the host is reachable." and "I can't verify whether the token works." pass with no try, because a `whether` clause reads as a fact. A hand-off in the next sentence passes too: "I can't check whether it works. You'll need to run the import yourself." Main passes these too. Harm: the owner is handed a step the session could do.
- **Where.** `lint/_clause.py` `judged_object`, which reads a `whether` clause as a fact. `lint/report_guard.py` `_claim` calls it.
- **Decision.** `cant-claim-needs-probe` (a cannot-claim for an act outside the table needs one probe).
- **Retire.** Each of the three inputs blocks with no try: the two claims, and the pair with the hand-off. A test in `lint/test_report_guard_cannot.py`, red on the current code first, expects those blocks.
