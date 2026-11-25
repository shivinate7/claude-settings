# The pass cache serves a pass from before a new file is added

**What.** The pass cache key in the CI job runner `bin/ci-job` is `tree_key`, a `git add -A` on a temp copy of the index. The key reads the same before and after `git add`, since the temp copy already takes in an untracked file. The code check reads only tracked files (`git ls-files -z`). So a pass saved while a new file was untracked is served after the file is added: a ruff error in that new file reads PASS until the cache is bypassed with `CI_JOB_NO_CACHE=1`. Claude meets it when it runs `bin/cheap-lints`, adds a new file, and runs it again.

**Where.** `bin/ci-job`, `tree_key()` and `cache_key()`. The file list is read in `actions/code-check/code_check.py`.

**Decision.** `lanes-run-no-full-ci-job`. The lane lint runs the lint steps through `bin/ci-job`, and the pass cache serves a saved pass for them.

**Retire.** The key changes when a file is added to the index. `lint/test_ci_job.py` gets a red case: a new untracked file with a lint error, a saved pass, then `git add` reads FAIL, not PASS. The fix PR deletes this file.
