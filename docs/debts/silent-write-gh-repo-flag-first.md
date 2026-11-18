# The silent-write rule misses `gh pr -R o/r merge`

**What.** `silent_write_hit` reads the raw first two words after `gh` (`rest[:2] == ["pr", "merge"]`), not `gh_call_of`. So `gh pr -R o/r merge 12 >/dev/null` passes, and `gh pr merge 12 -R o/r >/dev/null` is refused. Mistake: Claude writes the repo flag after the group word. Harm: a silenced merge, with its refusal and its proof of landing hidden, is not refused. Reported 2026-11-09 (lane gh-write-repo-flag-gap); read again on main.

**Where.** `hooks/guard.py`, `silent_write_hit`; `gh_call_of` in `hooks/guard_merge.py` is the one home that moves the repo flag.

**Decision.** `none`.

**Retire.** `silent_write_hit` reads the call through `gh_call_of`. A red case, `gh pr -R o/r merge 12 >/dev/null`, expects a refusal. Test file: `hooks/test_guard.py`.
