# A branch delete after its archive push needs no second ask

## Ruling

The installed settings carry one auto-mode allow entry, "Archived Branch Delete". It tells Claude Code's auto-mode classifier that a branch delete is lossless in two cases:

- Earlier in the session, the agent pushed that branch to `archive/<branch>` on the same remote, with no later commit, reset, rebase or amend on it.
- The branch is already in the default branch: `git branch -d`, or a branch whose pull request the session merged.

It never covers an `archive/` ref, the default branch, a tag, a release, a force push, or a branch whose archive push the session did not run.

Why: the guard's remedy (`guard_branch_worktree.BRANCH_DELETE_DENY_REASON`) hands over the archive push and the delete as commands. The classifier's built-in "Git Destructive" rule still asked the owner about the delete. That broke `shared-trees-archive-then-delete` (once the push succeeds, delete with no question).

- Risk: named incident. On the Mac, the probe branches of c53 (the cloud merge tool) were archived, then the deletes were refused and the owner was asked again.
- Home: `settings.json` `autoMode.allow`. The classifier reads `autoMode` only from `~/.claude/settings.json`, managed settings or `--settings`, never from a repo's `.claude/settings.json`. `install.sh` links or copies this repo's `settings.json` there.
- Check: `hooks/test_auto_mode_allow.py`. It reads the remedy's commands from the guard constant and fails until the entry quotes each one. It also fails an `autoMode` list that drops `$defaults`.
- Cost: none at run time. The classifier already runs; the entry adds prose to its prompt.
- The classifier sees commands, not their output. A failed archive push followed by a delete is still allowed by this entry. The guard's own remote-contains test still refuses the local `git branch -D` then.

Kind: process
Home: rule:shared-trees-archive-then-delete
