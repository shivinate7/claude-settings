# A list-form subprocess call ignores a PATH shim on Windows

## The ruling

A blind-command fixture cannot shadow a real executable for a list-form subprocess call on Windows. An arm that depends on that shadowing skips there, with a reason that names `CreateProcess` and points at this entry. It still runs and asserts on POSIX, where the shadowing is real.

- Why: `shutil.which("git")` finds a `git.cmd` shim first, but `subprocess.run(["git", ...])` still runs the real `git.exe`. Windows `CreateProcess` appends only `.exe` for a bare command from a list and never consults `PATHEXT`. Only `shell=True` reaches the shim.
- Why: `hooks/guard.py`'s `_git` calls `subprocess.run` with a list, never `shell=True`. An arm that cannot be driven proves nothing (`Trust a guard only once it goes red on the defect it guards`). Leaving it to fail proves a fixture gap, not the refusal the arm checks.
- The arms: `subject_unread_log_case` in `hooks/test_guard.py` (returns `True, "skipped: a stand-in git is not reached through CreateProcess"` on Windows), and `test_unreadable_worktree_status_refuses_too` in `janitor/test_install_launchd.py` and `janitor/test_install_schtasks.py` (`@unittest.skipIf` on Windows).
- The `git.cmd` sibling next to each blind `git` stays, because the shell-form arm in `hooks/test_guard.py` still needs it.
- `hooks/mutate_guard.py` carries the same shape for its mutants as a sixth tuple field, `only_on`.

Kind: process
Home: hooks/test_guard.py
