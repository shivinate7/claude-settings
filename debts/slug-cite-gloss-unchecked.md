# A cite by slug id carries no gloss check

- **What.** The report gate checks only `D<n>`-style ids for a short gloss. A slug id passes with no gloss check, so a bare slug cite breaks `speak-cite-id-plus-gloss` unseen.
- **Where.** `lint/report_gate.py`, rule `speak-cite-id-plus-gloss`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** The report gate checks slug ids for a gloss, and a test in `lint/test_gates.py` goes red on a bare slug.
