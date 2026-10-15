# The sweep tests error on Windows without symlink rights

- **What.** On a Windows host with no symlink right, two tests in `janitor/test_sweep.py` stop with WinError 1314. They report errors, not skips. Main and lane cut-tests-misc show the same 2 errors.
- **Where.** `janitor/test_sweep.py`, the cases that call `os.symlink` with no Windows skip.
- **Decision.** `test-strategy-reset` (a skipped test reports SKIP with a count).
- **Retire.** Each such case skips with a reason when the host refuses a symlink, and the run counts the skip.
