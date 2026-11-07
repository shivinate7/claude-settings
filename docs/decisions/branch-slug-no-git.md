# A new branch name has no git part

## The ruling

Coordinator, 2026-11-07 14:51 CST: a new branch name has no `git` part. Existing branches keep their names. The guard refuses a git act that creates a branch whose name has `git` as a whole part.

- A part is a piece of the name split on `-`, `_`, `/` and `.`. A part counts when it is exactly `git`, in any case. `git-push-fix`, `fix/git-hooks`, `git_x`, `wip.git` and `Git-x` are refused. `github-pin`, `digit-parse` and `fix.gitignore` pass.
- The acts: `switch -c|-C`, `checkout -b|-B`, `branch <new>`, and `worktree add -b|-B`. A `branch` call with a delete, rename, list or edit flag, or no name, is not a creation and passes. A copy (`branch -c|-C`) creates a branch, but the rule does not read it (see Misses).
- A rename (`branch -m old git-new`) passes. A switch to an existing git-named branch passes.
- Bash and PowerShell are judged the same way. Quoted text, a comment and a heredoc body are not an act.
- The remedy names a slug with no `git` part and never prints the refused name.

Why: Claude Code's built-in worktree isolation check (CLI 2.1.319) refuses an isolated agent's git command that names such a branch, with the text "names git more than once in a single command, which cannot be verified to stay inside the worktree". That check is in the CLI, not in this repo, so a hook cannot lift it. Lane `git-push-after-failed-commit` hit it three or more times on 2026-11-07.

Workaround for an old branch: push with `HEAD:<branch>`, and fetch with the default refspec.

Misses, by design: a rename, a branch made by `git push` to a new remote name, a `worktree add <path>` that names its branch from the folder, and `create_session`'s `outcome_branch`.

Misses, not by design, tracked in debt `branch-slug-no-git-forms`: a copy (`branch -c|-C`), `--orphan`, short flags bundled with the create flag (`-qb`, `-fc`), and a name held in a shell variable.

Cost: no git read and no file. A text check on calls that already parse git (`git_calls`), once per segment.

Protected by the `branch-slug-no-git` block in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py
