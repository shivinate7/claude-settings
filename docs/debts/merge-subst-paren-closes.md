# A quoted `)` or a pipe inside a command substitution hides merge flags from the guard

**What.** The merge-confirm-repo clause finds the end of a `$(…)` in shlex-unquoted text, so two forms close the span early and get through:

- (a) A quoted `)` inside it: `merge -C /other $(echo ')') --confirm` is not judged at all, because the cut drops `--confirm`. `$(echo ")")` does the same.
- (b) A pipe inside it: `merge 5 --confirm --base-red-ok $(date | cat) -C /other` is judged in the cwd repo, not `/other`. A value piped inside `$(…)`, such as a PR number from `gh pr list`, is a likely shape.

A plain, nested or quoted `$(…)` is already denied.

**Where.** `hooks/guard_merge.py`, `_command_words` and `_open_substitutions`, used by `_unproved_confirm`.

**Decision.** merge-confirm-repo (a cloud merge acts only in a repo its own record names).

**Retire.** The three cases in `hooks/test_guard.py` section 5h that deny the forms above, when the own record names only the cwd repo, pass.

Fix: step:merge-subst-paren (a queued roadmap step). Until: 2026-11-21
