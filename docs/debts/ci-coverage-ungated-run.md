# A test whose CI step cannot fail a pull request still counts as covered

- **What.** CiCoverage counts a test file as covered when any `run:` line names it. A step with `continue-on-error: true`, or with an `if:` that is always false, runs the file, or skips it, without ever failing a pull request. A session that adds `continue-on-error` to reach green leaves the file looking covered.
- **Where.** `run_commands` and `names_path` in `lint/test_windows_split.py`. Only the mod-test step is barred from this form, by `mods_step_problems`.
- **Decision.** None.
- **Retire.** CiCoverage skips a step with `continue-on-error: true` or an always-false `if:`, with a case for each in `lint/test_windows_split.py`.
- **Fix.** PR #2004 (ci-coverage-gated-steps)
