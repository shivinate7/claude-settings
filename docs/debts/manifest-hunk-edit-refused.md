# A builder's per-hunk resolve of a package.json conflict is refused

**What.** A builder that resolves a two-hunk package.json merge conflict with one Edit per hunk is refused at the first hunk. The file still holds markers after that Edit, so it does not parse, and an unparseable new text counts as an owned change. The refusal gives the test-author route, though no owned part changed. One Edit or one Write of the whole file passes. Main allowed both forms.

**Where.** `hooks/guard.py`, `owned_config_edit` and `owned_config_changed`. Found in PR #2103 review round 3.

**Decision.** `builders-cannot-edit-tests` (a builder never changes a test or test config).

**Retire.** Run `hooks/test_manifest_hunk_edit.py`. It must go green. It runs one case in `tests/guard/s21304-diff.py`: "builder-test: Edit that resolves the version hunk of a two-hunk package.json conflict is allowed". That case is red today. A sibling case, where an Edit that resolves the `jest` hunk is refused, stays green. The allow case registers only when `GUARD_HELD_CASES=manifest-hunk-edit-refused` is set. `hooks/test_manifest_hunk_edit.py` sets it and runs `hooks/test_guard.py` for that one case. CI runs `hooks/test_guard.py` without the gate, so CI never sees the case. The retire check runs the file, which sets the gate itself.
