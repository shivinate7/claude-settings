# A push of HEAD to a branch of another name is not guarded yet

**What waits.** A rule that refuses `git push <remote> HEAD` when the current branch tracks a
branch of a different name on that remote. HEAD pushes under the local branch's own name. The
push makes a stray branch on the remote, reports success, and leaves the tracked branch
untouched. Banchi measured this incident and recorded it in `scripts/guard-shell.py` in
banchi, in the push clause, dated 2026-09-12.

**Why it waits.** Banchi's own copy of the rule was overridden with its hatch 4 times since
2026-09-29. Unmeasured: how many of the 4 were false alarms and how many were real intent. The
owner held this rule on 2026-10-02 until Banchi reports. A rule that cries wolf is spent
(`guard-that-cries-wolf-is-spent`).

**The design, so the work is not lost.** Resolve the act, not the text.
- Match `git push <remote> HEAD` only. A refspec with a colon names its destination and is
  allowed. A branch named outright is allowed. `--all`, `--mirror`, `--tags`, `-d`, `--delete`
  are not this rule.
- Strip quotes from each argument, so `"HEAD"` is still HEAD.
- Read the branch with `symbolic-ref --short HEAD`. A detached HEAD gives no opinion.
- Read `branch.<name>.remote`. It must equal the pushed remote, else no opinion.
- Read `branch.<name>.merge`. No value, or a value equal to the branch name, is allowed.
- Allow when the tracked name is the remote's default branch. A branch cut from the default
  branch tracks it from birth, and its first push is meant to create its own name. The default
  comes from `refs/remotes/<remote>/HEAD`, else the first local branch of `main`, `master`.
- A failed or timed-out git read allows (fail-open). The harm is a stray branch that is visible
  in git's `[new branch]` line and is removed by one delete.
- Remedy text gives the form `HEAD:<branch-name>` with a placeholder, and names no branch.
- Cost: 2 to 4 git reads, only on a push of HEAD. Measured +20 ms on that command alone.
- Cases and mutants were written and passed on branch `guard/banchi-shell-traps` at commit
  15e7b85 (`push-head:` cases, fixtures `TRAPDIFF`, `TRAPSAME`, `TRAPCUT`). Recover the code
  from that commit.

**Trigger that brings it back.** Banchi reports its 4 hatch uses. If at least one was a real
stray-branch incident, or all 4 were intent the rule could tell apart, restore the rule from
15e7b85. If all 4 were false alarms of one shape, narrow the predicate to exclude that shape
first, and name the shape in the rule's comment.

**Owner.** The claude-settings orchestrator that takes the next Banchi guard change.
