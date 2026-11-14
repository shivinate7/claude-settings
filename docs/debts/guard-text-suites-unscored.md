# The mutation report never scores guard.py against three suites that read its text

**What.** A change to `hooks/guard.py` is mutated in a copy that went through `ast.unparse`, which drops comments. `lint/test_layout.py`, `hooks/test_wrappers.py` and `lint/test_report_guard_stamped.py` assert on `guard.py`'s own text, so each reads not green on that clean copy and cannot kill a mutant. `merge/test_merge.py` is dropped too: it timed out at 180 s on the clean source. So a mutant that only those four suites would catch counts as not run, and the catch share for `guard.py` reads higher than the full suite would give.

**Where.** `hooks/mutate_guard.py`, `GUARD_MODULE_DROPPED_SUITES`.

**Decision.** `mutation-report-scores-suites`, the report scores suites and a suite not green on clean source is not a killer. Its `guard.py` family row and dropped suites are stated in `mutation-ci-report-and-replay`.

**Retire.** The report mutates `guard.py` without dropping comments, or scores those suites some other way, and `GUARD_MODULE_DROPPED_SUITES` holds no row for it, shown by `hooks/test_mutate_ci.py`.
