# A push of HEAD to a branch of another name is not guarded

**What.** `git push <remote> HEAD`, when the current branch tracks a branch of another name on that remote, pushes under the local branch's own name. It makes a stray branch on the remote, reports success, and leaves the tracked branch untouched. Banchi measured this (2026-09-12, `scripts/guard-shell.py`, push clause).

**Where.** `hooks/guard.py`, the Bash push rules. No rule reads this case yet.

**Decision.** none. See the Ruling below.

**Retire.** Restore the rule, with its `push-head:` cases and mutants (fixtures `TRAPDIFF`, `TRAPSAME`, `TRAPCUT`), from commit 15e7b85 on branch `guard/banchi-shell-traps`. Design:

- Match `git push <remote> HEAD` only. A colon refspec, a named branch, `--all`, `--mirror`, `--tags`, `-d` and `--delete` are not this rule. Strip quotes from each argument.
- Read the branch with `symbolic-ref --short HEAD` (detached: no opinion). `branch.<name>.remote` must equal the pushed remote, else no opinion.
- `branch.<name>.merge` unset, or equal to the branch name, allows. A tracked name equal to the remote's default branch allows (`refs/remotes/<remote>/HEAD`, else the first local `main`, `master`).
- A failed or timed-out git read allows. The remedy gives `HEAD:<branch-name>` with a placeholder and names no branch.
- Cost: 2 to 4 git reads, only on a push of HEAD; +20 ms measured.

The check is a push of HEAD to a differing tracked name refused, and the allowed shapes above allowed.

## Ruling

Owner, 2026-10-02: hold this rule until Banchi reports its hatch uses. Banchi's own copy was overridden 4 times since 2026-09-29; unmeasured how many were false alarms. A rule that cries wolf is spent (`guard-that-cries-wolf-is-spent`). If at least one was a real stray-branch incident, or all 4 were intent the rule could tell apart, restore it from 15e7b85. If all 4 were false alarms of one shape, narrow the predicate to exclude that shape first, and name the shape in the rule's comment.
