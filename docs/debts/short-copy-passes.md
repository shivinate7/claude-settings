# A copied grant line under 12 words passes restates

**What.** A child line that copies a claude-settings grant in under 12 words passes the restates group. The group refuses only a unit that shares at least 12 words with a record. Example form: a two-sentence line that says who merges. Measure: unmeasured.

**Where.** `lint/compliance_probes.py`, probe group `restates`: the 12-word floor (`SHARED_MIN`) on shared words per unit.

- **Decision.** `child-cites-not-copies` (a child repo names, never copies).

**Retire.** Not yet built. Write a test in `lint/test_compliance_probes.py`, red on the current code first. It gives the restates group a child line under 12 words, copied from a record, and expects a refusal. The same test must still pass a repo-only rule that cites a record with its ruling time.
