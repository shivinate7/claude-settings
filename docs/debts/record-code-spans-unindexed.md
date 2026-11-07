# Owner words in record code spans are never indexed

**What.** The restates check strips code spans from the record side too, so owner words that a record keeps in backticks are never indexed. A copy of 12 or more of those words passes. Measure: unmeasured.

**Where.** `lint/compliance_probes.py`, probe group `restates`: `plain_words` strips code spans (`STRIPPED`) from each record unit, so `record_index` never holds their five-word runs.

- **Decision.** `child-cites-not-copies` (a child repo names, never copies).

**Retire.** Not yet built. Index code spans on the record side. Write a test in `lint/test_compliance_probes.py` first, red on the current code. It gives the restates group a child line that copies 12 or more words of a record's code-span text, and expects a refusal.
