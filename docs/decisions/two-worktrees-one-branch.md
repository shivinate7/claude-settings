# Two worktrees never hold one branch

## The ruling

Coordinator, 2026-11-07 14:29 CST, under lane override-plain-ask: the incident below gets its guard now. Orchestrator's call, not an owner grant: the checkout, switch and worktree-add forms, and their refusal.

Owner, 2026-11-09 20:25 CST, asked for the roadmap step `branch-force-other-worktree`, which adds the forced `branch` and `update-ref` forms below.

The guard rule `two-worktrees-one-branch` refuses a git command that checks out or re-points a branch another worktree of the clone already holds. The forms are:

- `git checkout -B <branch>`, and `git switch -C <branch>` or `--force-create <branch>`. Git 2.43 lets them through with no warning.
- `git checkout --ignore-other-worktrees` and `git switch --ignore-other-worktrees`, with any branch.
- `git worktree add -f` (or `--force`) for a branch.
- `git branch -f` or `--force` for a branch, or `-f` in a short-flag cluster such as `-fX`.
- `git update-ref [-m <msg>] refs/heads/<branch>`. Git 2.43 lets it through with no warning.

Not refused, by design: `branch` in a delete, move, copy, list or show mode (`-d`, `-D`, `-m`, `-M`, `-c`, `-C`, `-l`, `-L`, `--list`, `--delete`, `--move`, `--copy`, `--edit-description`, `--show-current`); `update-ref -d` and `update-ref --stdin`; tags and any ref outside `refs/heads/`. These are not forms Claude writes by mistake (decision `guard-guards-mistakes-only`: guards stop Claude's mistakes, not an attacker).

The guard reads `git worktree list --porcelain` once, only for the `-B`, `-C`, forced-add, forced `branch` and `update-ref` forms (`git_reads.clone_worktrees`). It does not run for any other command. For these forms, a branch that no other worktree holds passes. `--ignore-other-worktrees` is refused with any branch, because Claude has no need for it. Each git call in a chain is judged on its own. Its tree is its own `git -C <dir>` tree, else the cwd after the chain's earlier `cd` steps. Only a worktree other than that tree counts. A read that fails refuses, because the act is not one Claude needs to make blind. A folder outside any clone passes, because git refuses the call there itself. A forced add reads the branch from `-b` or `-B`, else the commit-ish, else the path's last name, as git does. A forced `branch` reads the first word that is no option. `update-ref` reads the name after `refs/heads/`; a ref outside `refs/heads/` passes.

## The incident

On 2026-11-07, in lane override-plain-ask, a builder agent's worktree held `lane/override-plain-ask`. The lane session then ran `git checkout -B lane/override-plain-ask origin/lane/override-plain-ask` in its own worktree, and git allowed it. Each commit in one tree then moved the branch under the other tree. The other tree's files and index stayed at the old commit and showed as a staged change. A commit there would have undone the builder's fix.

Three more lanes hit the same form on 2026-11-07: lint-uses-pinned-tools, notes-fix-other-1 (three times), and closure-stable-keys. Each ran `git checkout -B <b> origin/<b>` (or `-B <b> <sha>`) while another worktree held `<b>`. In closure-stable-keys, that other tree was the lane session's own.

## Harm it stops

A commit from the stale tree reverts work silently, and the diff looks like a normal edit.

`update-ref` on a held branch moves it under the other tree the same way, and Git 2.43 does not refuse it. Git 2.43 refuses a forced `branch` on a held branch itself, so that form is a second check. These git facts date this record: re-probe them when git changes.

Remedy the refusal prints: in your own worktree, run `git -C <own worktree> checkout --detach origin/<branch>`, commit there, then `git -C <own worktree> push origin HEAD:<branch>`. It names the worktree with `-C`, because a shell's cwd can reset to the pointer checkout (coordinator, 2026-11-07 17:20 CST, from lane pointer-head-own-detach). To read the other tree, use `git -C <dir>`.

Kind: build
Plan: docs/decisions/two-worktrees-one-branch.md#the-ruling (all)
