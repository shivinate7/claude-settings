# A failed commit mid-call passes the push guard

- **What.** A commit that fails mid-call, before a command that passes, such as `git commit -m ""; git status`, leaves the call's `is_error` false. The guard reads only `is_error`, so it allows a push beside that commit.
- **Where.** `push_after_failed_commit_hit` in hooks/guard_push_delete.py, which reads only `is_error`.
- **Decision.** `push-after-failed-commit` (a push beside a failed commit is refused).
- **Retire.** The guard reads the commit's own outcome, and a case with a failing commit before a passing command goes red, then green.
