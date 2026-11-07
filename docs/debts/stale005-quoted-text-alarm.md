# STALE005 reads quoted text and file paths as claims

**What.** STALE005 reads a quoted old claim and a grant title as claims. On the r2 records branch (commit 5b2d5397), 2 of 2 hits were false alarms: a quoted old claim at `docs/decisions/claims-carry-backing.md` :22, and the grant title "Acts the cloud refuses" at :60.

**Where.** `lint/stale_cites.py`, the STALE005 check (the route-claim check).

- **Decision.** `claims-carry-backing` (claim backing, STALE005 section).

**Retire.** STALE005 does not judge a quoted span or a file path as a claim. Closed when a test feeds the two r2 lines (the quoted old claim and the grant title) and expects no hit, and a sentence that states a route claim still hits.
