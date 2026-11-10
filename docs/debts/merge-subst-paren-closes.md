# A command substitution in a merge hides its flags from the guard

**What.** The merge-confirm-repo clause reads an unquoted `$(…)` as the command's closing `)`. Two forms get through, at the head of PR #1166 and at this head alike:

- (a) `merge 5 --confirm --base-red-ok $(date) -C /other` is judged in the cwd repo, not `/other`. A quoted `"$(date)"` is denied.
- (b) `merge -C /other $(echo 5) --confirm` is not judged at all, because the cut drops `--confirm`. Form (b) is a likely mistake: a PR number taken from `$(gh pr list …)`.

**Where.** `hooks/guard_merge.py`, `_command_words` and `_glued_counts`, used by `_unproved_confirm`.

**Decision.** merge-confirm-repo (a cloud merge acts only in a repo its own record names).

**Retire.** The clause skips a `)` that closes a `$(` opened in the same segment. A case in `hooks/test_guard.py` denies both commands above when the own record names only the cwd repo.

Fix: step:merge-subst-paren (a queued roadmap step). Until: 2026-11-21
