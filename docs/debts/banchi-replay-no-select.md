# A banchi replay row does not say that every changed suite ran

- **What.** banchi has no per-file `select`, so every changed suite runs on each mutant. Its rows do not say so. A survivor may sit in code that no changed suite reaches, and a reader cannot tell which.
- **Where.** The `banchi` entry in `REPLAY_PROFILES` (`hooks/mutate_guard.py`) has no `select` key. `_select_suites` (`hooks/mutate_shared.py`) returns an empty note when `select` is missing.
- **Decision.** `mutation-report-scores-suites` (the mutation report scores suites).
- **Retire.** A missing `select` writes a row note that every changed suite ran. A fixture in `hooks/test_mutate_replay.py` pins that note.
