# A blocker reason in a cannot-claim line blocks as no try

**What.** The cannot-claim check skips a sentence only for until, before, without your, and the words rule, ruling, decision and grant. A line that gives a blocker as its reason has none of these, so it blocks as a claim with no try. Blocked examples: "I can't merge the PR because CI is red.", "I cannot merge it while the batch run is in progress.", "I can't push to main (git-main-only-by-pr)." Claude is likely to write such lines in batch and CI work, so the check refuses a true statement about a blocker.

**Where.** `lint/report_guard.py`, `CANNOT_DEPENDENCY_RE` (:1546) and `CANNOT_RULE_RE` (:1549), read by `_claim` (:1636).

**Decision.** `claims-carry-backing`, a definitive prose claim carries its backing or a route row. Its Part (vi), What it skips, lists the skip words.

**Retire.** Add the three example lines as cases to `lint/test_report_guard_cannot.py`. Each goes red on the current check and green after the fix. A plain "I cannot merge the PR." with no try and no cite still blocks.
