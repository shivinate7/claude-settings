# A decision and a deferred record with one stem collide in judge titles

- **What.** A `decisions/` record and a `deferred/` record with the same file stem collide in the rulings titles, because the title names the stem only.
- **Where.** The ruling block title in `hooks/question_outcome.py` (`RULINGS_DIRS` and the `Ruling of record` title).
- **Decision.** `question-judge-reads-rulings` (the question judge refuses a question the owner already settled).
- **Retire.** The title names the directory with the stem, and a test pins two records with one stem.
