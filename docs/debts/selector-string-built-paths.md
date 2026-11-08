# The suite selector misses a path built by string formatting

**What.** `--tests-for` and `--lint-suites` read a file load from the string constants of a path expression. Such an expression is a call to `open`, `shutil.copy*` or `subprocess.run`, an `os.path.join` or `Path` call, or a `/` expression. A path built by `%`, `+`, `.format` or an f-string is missed. A suite that opens `hooks/leaf.py` through `"hooks/%s.py" % name` is not selected for a diff of `hooks/leaf.py`.

**Where.** `_suite_profile` in `hooks/mutate_guard.py`.

**Decision.** `mutation-ci-report-and-replay`, the mutation report job and the known-defect replay.

**Count.** On 2026-11-08, 44 of the 118 tracked `test_*.py` built a path by string inside an `open`, `shutil.copy*`, `os.path.join` or `Path` call. A check of each such read, and of each such join under a checkout root, found two that reach a tracked file.

- `record()` in `lint/test_compliance_probes.py` reads `docs/decisions/<slug>.md` through `slug + ".md"`. So a diff of `docs/decisions/standing-merge-grant.md` does not pick that suite, though its cases read that record. A `+` fix alone would not pick it: `slug` is a parameter (debt `tests-for-misses-param-loads`, the selector misses a path passed as a parameter). Its `record_slugs()` also lists the folder, which no static form names.
- `actions/ste-lint/test_action.py` checks that `lint/<m>.py` exists, for module names it parses from `lint/ste_lint.py` at run time. No static form names those files.

**Retire.** The selector joins the strings of a `+` or `%` path expression and follows a path parameter to its call sites. A new case in `hooks/test_mutate_ci.py` (`LintSuitesChainTests`) then picks a suite that opens a file through `name + ".py"`, and `--tests-for docs/decisions/standing-merge-grant.md` prints `lint/test_compliance_probes.py`.

Fix: join `+` and `%` strings in a path expression, after debt `tests-for-misses-param-loads`; needs a test-author case first. Until: 2026-11-21
