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

Two process tiers are generic, and they live here. `find_loose_processes` is
report only: its subject is an orphaned process whose argv contains a
shell-snapshots path. A live session's wrapper is noise, so it is not listed. `find_dead_rooted` stops only a proven orphan that the current user owns.
Its subject is a process whose script file and its parent directory are gone,
under a deleted checkout. That names no repository's own files. Each repository's own live servers stay its own.

## Stale registrations are pruned by git's own word

Branches and worktrees are git's to judge, so the prune tier asks git. It runs
`git worktree prune -n -v` and acts only on what that names, and only under
`--confirm`. The sweep keeps no second rule for "stale". The tier runs before
the worktree list is read, so a pruned registration is never judged as a
worktree.

## A stale agent lock does not keep a worktree

The Agent tool locks each lane worktree with the reason
`claude agent agent-<id> (pid N start <UTC date>)`. The pid is the host Claude
process, not the agent: two agents share one pid, MEASURED. A lane always
commits, so the tool never removes it, and the lock outlives the agent. An
agent worktree therefore stays until its host session ends. The outcome to
protect is a lane's unpushed work. The sweep frees a worktree from such a lock
only when the host pid is dead, or alive with another start time. The worktree
must also pass every other check. Any other lock reason, and any unreadable
fact, keeps it.

Owner ruling: remove only a folder that is clean and fully pushed. This covers
every worktree reap, locked or not. Every commit on HEAD must be on a remote
branch, and a detached HEAD counts. The daily job reaped q_max agent
worktrees before this check existed. The count is unmeasured here.
`--confirm` unlocks, then removes, never with `--force`. If the removal fails,
the sweep restores the lock.

Unmeasured: q_max held no locked worktree when this was written, so the lock
format is measured from the live lanes of this repository only.

## A branch leaves "checked out" with its worktree, in the same run

Owner ruling: if the sweep removes a worktree, the branch it held is free.
The sweep then judges that branch by the normal no-unique-work rules, in the
same run. A preview does this for a worktree marked REAP. A kept worktree
keeps its branch held. A failed removal does the same. Before this ruling, the
branch waited one day.

## Two single-tier modes serve a hook

Owner ruling: `--tier1` and `--branches` let a session-end hook run one tier.
`--tier1` prunes stale registrations and deletes husks. It is the one mode
that acts without `--confirm`. It removes only proven junk, and a hook runs it. `--branches` reaps branches only and removes no worktree.
`--root PATH` names the repository by any path inside it. A linked worktree
is a valid path. `--branches` holds every worktree's branch. It refuses the
repository if git gives no worktree list.

## Leftover folders are deleted only when proven twice

`find_husks` finds a real folder under `.claude/worktrees/` that git does not
list as a worktree and that holds only names the repository gives in
`huskNames`. The repository knows its own build output. The sweep does not.
Only `--confirm` deletes, and only after the proof runs again right before the
delete. The sweep never follows a link, and it walks only the repository's own
`.claude/worktrees`, never a link out of it. Any error keeps the folder. An
empty process table keeps it too. The process check reads the current directory
only, so a process outside the folder that holds a file inside is not seen.
On Windows the tier stays report only: Python before 3.12 does not see a
junction as a link, and `rmtree` there has no symlink-attack guard.

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
