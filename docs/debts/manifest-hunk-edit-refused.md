# A builder's per-hunk resolve of a package.json conflict is refused

**What.** A builder that resolves a two-hunk package.json merge conflict with one Edit per hunk is refused at the first hunk. The file still holds markers after that Edit, so it does not parse, and an unparseable new text counts as an owned change. The refusal gives the test-author route, though no owned part changed. One Edit or one Write of the whole file passes. Main allowed both forms.

**Where.** `hooks/guard.py`, `owned_config_edit` and `owned_config_changed`. Found in PR #2103 review round 3.

**Decision.** `builders-cannot-edit-tests` (a builder never changes a test or test config).

**Retire.** A builder's Edit that resolves one hunk of a version-only package.json conflict is allowed, and a hunk that changes `jest` stays refused. `hooks/test_guard.py` holds both cases.
