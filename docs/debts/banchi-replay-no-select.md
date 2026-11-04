# A replay row does not say that every changed suite ran

- **What.** A profile with no `select` runs every changed suite on each mutant. Its rows do not say so. A survivor may sit in code that no changed suite reaches, and a reader cannot tell which.
- **Where.** `_select_suites` (`hooks/mutate_shared.py`) returns an empty note when `select` is missing.
- **Decision.** `mutation-report-scores-suites` (the mutation report scores suites).
- **Retire.** A missing `select` writes a row note that every changed suite ran. A fixture in `hooks/test_mutate_replay.py` pins that note.
