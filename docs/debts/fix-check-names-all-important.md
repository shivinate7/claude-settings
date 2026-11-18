# A fix check may name only some open Important findings

**What.** `review_state` in `merge/merge.py` reads each record's rounds, Fix check verdict and Fix check model. It reads no finding ids. So a PASS fix check that names only some open Important findings reads done, and the review ends with an Important finding still open.

**Where.** `merge/merge.py`, `review_state`. `agents/reviewer.md`, the Fix check paragraph, which states the rule that no code enforces.

**Decision.** `hold-unsafe-after-round-3` (the round rules and the fix check definition).

**Retire.** Not yet built. The finding ids below `---` must be read first: no code reads them today (decision `pr-review-record`, the review log form). Then `review_state` holds a PASS fix check that names fewer ids than the open Important findings. Write a case in `merge/test_merge.py` first, red on the current code: two open Important ids, a PASS fix check that names one of them, and `review_state` must read open.
