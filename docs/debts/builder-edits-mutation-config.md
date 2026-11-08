# A builder can edit the mutation test config

- **What.** `hooks/mutate_guard.py` is test config a test-author owns (`AUTHOR_MUTATION_TESTS`), yet the builder write check allows a builder to edit it. Seen in lane mixed-merge-resolver: a builder added three mutants and re-anchored one.
- **Where.** `role_write_hit` and `role_offences` in `hooks/guard.py`, builder branch: they read `is_test_rel` and test-runner config, not `AUTHOR_MUTATION_TESTS`.
- **Decision.** `builders-cannot-edit-tests` (builders cannot edit tests).
- **Retire.** A builder write or commit of a path in `AUTHOR_MUTATION_TESTS` is refused, shown by a case in `hooks/test_guard.py`.
- Fix: step:notes-fix-builder-mutants.
