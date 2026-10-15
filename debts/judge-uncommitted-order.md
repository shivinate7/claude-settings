# Uncommitted rulings sort after the listed ones in the judge

- **What.** A record git does not list (new and not committed) is ordered by file mtime, after the listed ones.
- **Where.** The ruling order in `hooks/question_outcome.py` (the git log call and the mtime fallback).
- **Decision.** `question-judge-reads-rulings` (the question judge refuses a question the owner already settled).
- **Retire.** A test pins where an uncommitted record sorts against the listed ones, and the order is decided by ruling.
