# The finder's test fixture git does not scrub GIT_DIR

- **What.** `GIT_ENV` in `lint/test_find_time_pinned.py` sets `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` to the null device and keeps every other variable from the caller. An inherited `GIT_DIR` (or `GIT_WORK_TREE`, `GIT_INDEX_FILE`) takes precedence over the folder that `git -C self.root` names, so the fixture's `--base` cases can act on the caller's repo.
- **Where.** `lint/test_find_time_pinned.py`: `GIT_ENV`, and the fixture `git` helper that passes it. `lint/test_check_red_run.py` (the loop near line 83) pops `GIT_DIR`, `GIT_WORK_TREE` and `GIT_INDEX_FILE` from its environment, which this file does not do.
- **Decision.** `git-env-set-refused` (a shell that sets a git location variable points child git at another tree; a child scrubs every `GIT_*` name).
- **Retire.** `lint/test_find_time_pinned.py` has a case that runs a fixture with `GIT_DIR` set to another repo, and passes because `GIT_ENV` drops it.
