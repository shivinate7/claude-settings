# The suite selector misses a path built by string formatting

**What.** `--tests-for` and `--lint-suites` read a file load from the string constants of a path expression. Such an expression is a call to `open`, `shutil.copy*` or `subprocess.run`, an `os.path.join` or `Path` call, or a `/` expression. A path built by `%`, `+` or `.format` is missed. A suite that opens `hooks/leaf.py` through `"hooks/%s.py" % name` is not selected for a diff of `hooks/leaf.py`.

**Where.** `_suite_profile` in `hooks/mutate_guard.py`.

**Decision.** `mutation-ci-report-and-replay`, the mutation report job and the known-defect replay.

**Retire.** The selector reads the strings of a `%`, `+` or `.format` path expression, or the suites that load a file this way name it in a form the selector reads. A new case in `hooks/test_mutate_ci.py` (`LintSuitesChainTests`) then picks a suite that opens a file through `"%s.py" % name`.

Fix: none — no tracked suite loads a file through a string-built path (0 of 118 test_*.py; 4 build one only to probe or write). Until: 2026-11-21
