# The suite selector misses a path built by string formatting

**What.** `--tests-for` and `--lint-suites` read a file load only from the string constants of a path expression: an argument of `open`, `shutil.copy*`, `subprocess.run` and the like, an `os.path.join` / `Path` / `/` expression, and the names they hold. A path built by `%`, `+` or `.format` is missed, so a suite that opens `hooks/leaf.py` through `"hooks/%s.py" % name` is not selected for a diff of `hooks/leaf.py`.

**Where.** `_suite_profile` in `hooks/mutate_guard.py`.

**Decision.** `mutation-ci-report-and-replay`, the mutation report job and the known-defect replay.

**Retire.** The selector reads the strings of a `%`, `+` or `.format` path expression, or the suites that load a file this way name it in a form the selector reads. A new case in `hooks/test_mutate_ci.py` (`LintSuitesChainTests`) then picks a suite that opens a file through `"%s.py" % name`.

Fix: none — no tracked suite loads a file through a string-built path (0 of 118 test_*.py; 4 build one only to probe or write). Until: 2026-11-21
