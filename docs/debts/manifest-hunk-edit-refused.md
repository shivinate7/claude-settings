# A builder's per-hunk resolve of a package.json conflict is refused

**What.** A builder that resolves a two-hunk package.json merge conflict with one Edit per hunk is refused at the first hunk. The file still holds markers after that Edit, so it does not parse, and an unparseable new text counts as an owned change. The refusal gives the test-author route, though no owned part changed. One Edit or one Write of the whole file passes. Main allowed both forms.

**Where.** `hooks/guard.py`, `owned_config_edit` and `owned_config_changed`. Found in PR #2103 review round 3.

**Decision.** `builders-cannot-edit-tests` (a builder never changes a test or test config).

**Retire.** Run `hooks/manifest_hunk_edit_test.py`. It must go green. It runs one held case: "builder-test: Edit that resolves the version hunk of a two-hunk package.json conflict is allowed". The case lives in `tests/held/s21305-held.py`, outside the folder CI runs. The file copies `tests/guard/*.py` and that held file into a temp folder, sets `GUARD_SECTION_DIR` and `MUTATE_ONLY`, and runs `hooks/test_guard.py`. The case is red today. The sibling case in `tests/guard/s21304-diff.py`, where an Edit that resolves the `jest` hunk is refused, stays green in the CI section. CI has no step for this file on purpose, since it stays red until the debt closes.
