# The janitor, for a repository it sweeps

This guide is for the owner of a repository on this machine. It states what
the sweep does to your repository, how you change that, and how you add a tier
of your own.

`janitor/sweep.py` reaps local branches that hold no unique work, and removes
worktrees that no session still uses. It runs against every repository on this
machine.

## What it never does

The sweep never touches a remote. It runs no push, and no fetch.

The sweep never stops a running program.

The sweep never runs code that your repository supplies. It reads one file
from your repository, and it reads that file as data.

The sweep deletes no branch that holds the only copy of its work.

## How it decides

The sweep reads the state of each subject. It matches no list of names.

A branch is reapable when the default branch already contains it, OR when
`git cherry` finds every patch on the default branch. `git cherry` compares
patch ids, so it sees through a rebase, where a commit id no longer matches.

The sweep keeps a branch, and names it as the only copy, when a patch survives
that test and no remote ref carries the branch.

The sweep resolves your default branch in this order: `origin/HEAD`, then local
`main`, then local `master`. If none of the three answers, the sweep refuses
your whole repository and reaps nothing in it.

## What it refuses

The sweep keeps a branch under a protected prefix. `backup/` is the default.

The sweep keeps a branch that any worktree checks out.

The sweep keeps `main`, `master` and the default branch itself.

The sweep keeps a worktree that holds uncommitted or untracked work.

The sweep keeps a worktree that a live session stands in.

The sweep keeps a worktree that holds a lock, and it names the holder.

The sweep keeps any subject that it cannot read. An unreadable session record,
a `git worktree list` that fails, or a `git status` that fails each mean keep.

## How you opt out

Write `.claude/janitor.json` at the root of your repository:

    {
      "sweep": false,
      "protectedPrefixes": ["archive/", "wip/"]
    }

`sweep` must be the JSON literal `false` to opt out. A string, a number or a
null is not a `false`. The sweep then refuses your whole repository, the same
direction as an unreadable file, not a guess at what you meant.

`protectedPrefixes` is a list of strings. The sweep adds them to `backup/`,
and it never drops the default. A value that is not a list of strings also
refuses your whole repository, instead of silently protecting nothing.

Both keys are optional. A file that holds only `protectedPrefixes` stays swept,
and protects more names.

The sweep visits a repository that carries no file. The owner chose that
default.

A file that exists but holds no readable JSON object refuses your whole
repository. The sweep reaps nothing there, and it says so.

## How you get a branch back

The sweep writes `refs/janitor/reaped/<branch>` at the tip of every branch it
deletes, before the delete. It also appends one line to a restore log under the
Claude config directory.

Restore a branch with one command:

    git branch <name> refs/janitor/reaped/<name>

The tombstone lives 90 days. Until the purge step drops it, `git gc` cannot
take the commits.

## How you add a tier of your own

The sweep holds the generic half: branches and worktrees, which are pure git
plus a liveness read. It does not hold your servers, your background programs
or your own build output. Those name your repository, and they belong to you.

Write your own tier in your own repository. Call the generic sweep first, then
do your own work:

    python3 ~/.claude/janitor/sweep.py "$PWD" --confirm

Preview first. The sweep deletes nothing without `--confirm`, and the preview
names every decision with its reason.

Three rules your own tier must meet, because the generic half already meets
them:

1. Fail open in a hook. A hook that can refuse the end of a session is worse
   than the leak it cleans up.
2. Fail closed on a subject you cannot read. An unreadable subject means keep.
   The two rules above are not in conflict: the first is about how your hook
   EXITS, and the second is about what it DELETES.
3. Never stop a program that you did not start.
