# The janitor is one machine-wide sweep

Kind: process
Home: janitor/sweep.py

The sweep deletes a local branch when that branch holds no unique work. It
also removes a spent worktree. This entry
records where it lives, and what it leaves to each repository.

## The subject is the machine

The liveness oracle reads `~/.claude/sessions`, which is machine-wide. Worktrees
sit under many repositories at the same time. On 2026-09-20 this machine held
50 registered worktrees, spread over five repositories. 43 of them sat under
`.claude/worktrees/`. 10 were dirty, 8 were locked, and 6 held a live session.
The machine held no husk folder.

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
under a deleted checkout. That names no repository's own files. Each repository's own live servers stay its own. Banchi keeps its own tier 2 until the owner
names its removal.

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

The lock may also read `claude agent agent-<id> (pid N)`, with no start time. The sweep frees that form only when pid N is dead. It has no pid-reuse check, so a live process that holds a reused pid keeps the tree.

Owner ruling: remove only a folder that is clean, and whose work is safe. Work
is safe in two cases. Every commit on HEAD is on a remote branch, and a
detached HEAD counts. Or HEAD is merged into the default branch by ancestry or
by patch (owner ruling 2026-10-08). A squash-merged lane whose branch was deleted is
therefore removable. The merged exemption needs the repository to have a
remote; with none, every worktree stays. Accepted risk (owner, 2026-10-08): the patch
read matches any past commit on the default branch. If a lane's patch landed
and was later reverted, an unpushed sole copy still reads as merged and can be
removed. The owner chose the patch check over a check of the lines on main
today. This covers every worktree reap,
locked or not. Every `--confirm` run also applies the merged, pushed and idle limits of
`unattended-sweep-stops-proven-orphans` (an unattended sweep removes only proven orphans).
`--confirm` unlocks, then removes, never with `--force`. If the removal fails,
the sweep restores the lock.

Unmeasured: q_max held no locked worktree when this was written, so the lock
format is measured from the live lanes of this repository only.

## Every automatic run leaves a trace

Incident, 2026-10-07: drive C: in q_max fell to 2 GB free, and lanes failed
with ENOSPC. About 1,000 lane worktrees, each with its own `node_modules`, held
the space. A one-off cleanup freed about 270 GB. On 2026-10-08, q_max still held
368 worktrees that the sweep would remove. The daily task was never registered
on this Windows machine. The SessionEnd hook wrote no log, so nobody could tell
whether it ran.

Owner rulings, 2026-10-08:
- A `--confirm` run appends one line per repository to
  `${CLAUDE_CONFIG_DIR:-~/.claude}/state/janitor-runs.jsonl` (`JANITOR_RUN_LOG`
  overrides it): removed worktrees, reaped branches, and free disk bytes. A
  preview writes nothing. When the run removed anything, the report prints
  free disk.
- The sweep lists entries under `<root>/.claude/worktrees/` that git does not
  register, as strays. It never deletes them.
- The rule reads git's admin-file idle time, not folder mtime (idle as in
  `unattended-sweep-stops-proven-orphans`). It removes a worktree with git. It never calls a repository's WorktreeRemove hook.

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
Windows deletes too, since 2026-10-12: `sweep.is_link` reads a junction from the
reparse-point flag, because `os.path.islink` never sees one (decision
build-dirs-reaped-at-agent-end, "Builder decisions"). `rmtree` on Windows has no
symlink-attack guard (`shutil.rmtree.avoids_symlink_attacks` is False there, True on
POSIX), so on Windows a link swapped in after the read and before the delete is
not covered.

## The sweep never runs code a repository supplies

A repository states its wishes in `.claude/janitor.json`, and the sweep reads
that file as data. A repository that supplies code to a frozen tool can do
everything that tool can do.

## The measured reason this is not a copy

`~/.claude/bin/janitor.py` on this machine is a stale copy of a sibling
repository's sweep. It carries a different checksum from that repository's own
`main`, and the shim beside it runs the repository instead. That copy is the
outcome this entry exists to prevent.

## The sweep is automatic, and a repository opts out

The sweep visits every repository that carries no opt-out file. The owner accepted the cost on
2026-09-20. A repository with long-lived local branches loses them at the first sweep, unless
somebody adds the file first. The tombstone makes that loss recoverable.

The opt-out file is `.claude/janitor.json`, inside the repository. Three constraints pick this
place and this format:

- The file travels with a clone, so it does not sit in `.git/`.
- The sweep reads it as data and never runs it.
- It carries more than a yes or a no, so a bare marker file cannot do the job.

The repository that pays the cost holds its own consent. An absent file means swept. The keys
are in the janitor guide.

## The default branch

The sweep judges each repository against its own default branch. The janitor guide gives the
resolve order. If none answers, the sweep refuses the repository out loud and reaps nothing
there. On 2026-09-20 the repository `sillage` had an unset `origin/HEAD` with an `origin`
remote present, so the fallback ran on day one.

## Two triggers

A `SessionEnd` hook sweeps only the repository whose session ended. A daily scheduled job
sweeps every repository. The hook fails open, because a hook that can refuse the end of a
session is worse than a leak. The installers write the job definition outside the repository,
so nobody commits it. Each installer refuses to run from a linked worktree.

## A reaped branch leaves a tombstone

Before the delete, the sweep writes `refs/janitor/reaped/<branch>` at the tip. It appends one
line to a restore log: repository, branch, commit id, time. The commits stay reachable, so
`git gc` cannot take them. The purge drops a tombstone after 90 days.

The 90 comes from git, not from a fresh guess. Git expires an unreachable reflog entry after 30
days. It prunes a loose object after two weeks. A tombstone under 30 days buys nothing. Git
keeps a reachable reflog entry for 90 days, so the machine already uses the number. It also
covers a long absence.

The purge reads the age from the restore log's own timestamp, never from the mtime of the ref.
An mtime changes for reasons that have nothing to do with the reap. The restore point that the
purge keeps is in `purge-keeps-younger-restore-ref` (the purge keeps the younger restore ref).

## Liveness

Liveness comes from `~/.claude/sessions/*.json`. A record counts as live only when the id is
alive and the recorded start time still matches. A recycled id then cannot inherit a dead
session's claim. The oracle compares the start time as epoch milliseconds. A rendered clock
time carries a timezone, and that form of the test fails. The first measurement hit this trap:
a five-hour offset looked like a match.

## How the sweep is proven

- Each refusal gets a test arm that violates it. No refusal can weaken unseen.
- Every arm asserts that its subject set is not empty before it asserts a verdict. An arm that
  passes over an empty set proves nothing. That failure happened three times in the Banchi work.
- The anchor arm is the rebase ghost. It must go red against a keep rule that tests ancestry
  alone (`a-branch-is-redundant-by-patch-not-by-ancestry`, a branch is redundant by patch).
- The liveness arm holds a record whose stored start time does not match the live id. That arm
  must read the session as dead.
- Each assertion is mutated to show that it fails.
- Each new rule gets a row in `lint/rule_mechanisms.json`, or an argued `unmechanized` row.

## The mechanism

`lint/check_landed_dirs.py` holds the manifest and the frozen list in
agreement. `janitor/test_sweep.py` proves the sweep itself.
