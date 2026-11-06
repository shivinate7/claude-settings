# No test drives the route matcher's size limits

**What.** No test drives `MAX_TARGET_CHARS` or `MAX_PATTERN_CHARS`, so a change to either limit passes every test.

**Where.** `hooks/route_match.py` (the route matcher).

**Decision.** `claims-carry-backing` (the claim-backing record, its route row section).

**Retire.** A test drives each limit at its value and one past it, and checks the result. Closed when that test is in the suite and green.
