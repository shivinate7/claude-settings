# A list-form subprocess call ignores a PATH shim on Windows

Three suites drive a blind `git` stand-in through a directory placed first on `PATH`. Two
of them assumed that stand-in reaches the real `git` call on every platform. It does not,
on Windows. This entry names the platform fact and the rule it sets.

## What was measured

Measured on a real Windows 11 machine, with a `git.cmd` shim placed ahead of the real
`git.exe` on `PATH`:

```
shutil.which("git")                        -> the shim's git.CMD
subprocess.run(["git", "--version"])       -> exit 0, "git version 2.55.0.windows.3"
subprocess.run(["git", "--version"], shell=True) -> exit 128, the shim's own output
```

`shutil.which` finds the shim first. A list-form `subprocess.run(["git", ...])` still runs
the real `git.exe`, not the shim. Windows `CreateProcess` appends only `.exe` when it
resolves a bare command from a list. It never consults `PATHEXT`, so the `.cmd` sibling is
invisible to that call. Only the shell form, `shell=True`, walks `PATHEXT` and reaches the
shim.

## The suites this touches

`hooks/guard.py`'s `_git` calls `subprocess.run` with a list, never `shell=True`. Three
suites build a blind-`git` fixture meant to make some `guard.py` read fail, then assert on
the refusal that failure should cause:

- `hooks/test_guard.py`, `subject_unread_log_case`
- `janitor/test_install_launchd.py`, `RefusesWhenWorktreeStatusIsUnreadable`
- `janitor/test_install_schtasks.py`, `RefusesWhenWorktreeStatusIsUnreadable`

`hooks/test_guard.py` already carried the fix, at line 2397: on Windows it returns
`True, "skipped: a stand-in git is not reached through CreateProcess"`, instead of
asserting on a refusal the platform cannot produce. Neither installer suite carried it. Each
already wrote a `git.cmd` sibling next to its blind `git`, which was not enough, for the
reason measured above. Both failed the same arm, on this machine, with
`AssertionError: 0 == 0`.

## The rule

A blind-command fixture cannot shadow a real executable for a list-form subprocess call on
Windows. An arm that depends on that shadowing must not assert there. It skips on that
platform, with a reason that names `CreateProcess` and points at this entry. The arm still
runs, and still asserts, on POSIX, where the shadowing is real.

This follows CLAUDE.md directly: "Trust a guard only once it goes red on the defect it
guards." An arm that cannot be driven on a platform proves nothing there. Leaving it to
fail proves a fixture gap, not the refusal the arm exists to check. That failure shape
already has a name in `decisions/mutant-cause-of-death.md`. It is a shape of failure
standing in for the actual defect.

## The fix

`janitor/test_install_launchd.py` and `janitor/test_install_schtasks.py` now skip
`test_unreadable_worktree_status_refuses_too` on Windows, with `@unittest.skipIf`. The
reason names `CreateProcess` and points at this entry. Both `make_blind_git` docstrings are
corrected. They no longer claim the `git.cmd` sibling makes the shim reachable through a
list-form call. The sibling stays, because the shell-form arm in `hooks/test_guard.py`
still needs it.

`hooks/mutate_guard.py` carries the same shape for its own mutants, as a sixth tuple field,
`only_on`. That file is out of scope for this change. A different lane holds it.

## Holes, named

- `janitor/test_install_schtasks.py` was not wired into any CI job before this change. Its
  skip has never run on Windows CI. It is proven only on this machine, by hand.
- This entry does not audit every blind-command fixture in the repository for the same gap.
  `janitor/test_sweep.py`'s own `make_blind_git` may carry the identical assumption. That
  audit is not part of this change.
