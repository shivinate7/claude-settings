# The janitor is one machine-wide sweep

The sweep deletes a local branch when that branch holds no unique work. It
also removes a spent worktree. This entry
records where it lives, and what it leaves to each repository.

## The subject is the machine

The liveness oracle reads `~/.claude/sessions`, which is machine-wide. Worktrees
sit under many repositories at the same time. On 2026-09-20 this machine held
50 registered worktrees, spread over five repositories. 43 of them sat under
`.claude/worktrees/`.

Five copies of one sweep are five things that can each be wrong about the same
machine. One copy is the coherent shape, and this repository is where a
machine-wide tool belongs.

## What the parent ships

Branches and worktrees are pure git plus that oracle. They transfer to any
repository, so they land here, in `janitor/`.

The directory joins `landed-dirs.txt` and `CONFIG_FROZEN_DIRS` in
`hooks/guard.py` in the same change. A session must not rewrite a program that
deletes branches. The frozen claim is the reason to add the directory, and not
the cost of it.

## What a child repository keeps

A process tier and a service teardown name one repository's own files, its own
servers and its own launchd labels. They do not transfer. Each repository
keeps its own tier, and this repository ships the guide for writing one.

## The sweep never runs code a repository supplies

A repository states its wishes in `.claude/janitor.json`, and the sweep reads
that file as data. A repository that supplies code to a frozen tool can do
everything that tool can do.

## The measured reason this is not a copy

`~/.claude/bin/janitor.py` on this machine is a stale copy of a sibling
repository's sweep. It carries a different checksum from that repository's own
`main`, and the shim beside it runs the repository instead. That copy is the
outcome this entry exists to prevent.

## The mechanism

`lint/check_landed_dirs.py` holds the manifest and the frozen list in
agreement. `janitor/test_sweep.py` proves the sweep itself.
