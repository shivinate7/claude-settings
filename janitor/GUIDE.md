# The janitor, for a repository it sweeps

This guide is for the owner of a repository on this machine. It states what
the sweep does to your repository, how you change that, and how you add a tier
of your own.

`janitor/sweep.py` reaps local branches that hold no unique work. It removes
worktrees that no session still uses. It also signals an orphaned TCP listener
left behind inside a repository it covers. It prunes stale worktree
registrations. It deletes leftover folders. It runs against every repository on
this machine.

## What it never does

The sweep never pushes. It reads each remote with `git ls-remote`. In each
repository it judges, except with `--tier1` or past the run deadline, it first
runs `git fetch --prune --no-tags`, in a preview too. The fetch moves
remote-tracking refs only: no local branch, no tag, no working tree.

The sweep never stops a program a live session still needs. It can stop three
kinds. The first is an orphaned TCP listener inside a repository or worktree this
sweep covers. The second is an orphaned dead-rooted server. The third is an iOS
simulator that a session booted. The first two must be owned by the account
running the sweep. See "Orphaned TCP listeners" and "Dead-rooted servers" below.
A simulator is machine-wide. The sweep stops only a device that a session booted,
that is idle, and that the owner did not boot (decision
`sweep-shuts-down-idle-simulators`, the sweep stops idle simulators).

The sweep never runs code that your repository supplies. It reads one file
from your repository, and it reads that file as data.

The sweep deletes no branch that holds the only copy of its work.

## How it decides

The sweep reads the state of each subject. It matches no list of names.

A branch is reapable when the default branch already contains it, OR when
`git cherry` finds every patch on the default branch. The sweep keeps a branch,
and names it as the only copy, when a patch survives that test and no remote ref
carries the branch. See decision `a-branch-is-redundant-by-patch-not-by-ancestry`
(a branch is redundant by patch).

The sweep resolves your default branch in this order: `origin/HEAD`, then
`origin/main`, `origin/master`, local `main`, local `master`. If none of the
five answers, the sweep refuses your whole repository and reaps nothing in it.
See decision `default-branch-read-order` (the default-branch read order).

## How it picks repositories

Pass roots on the command line, or `--discover DIR` to sweep one directory's
own checkouts.

With neither, the sweep reads `janitor.roots` from this repository's own
`settings.json`. Set it to a list of paths, and the sweep discovers only
those:

    {
      "janitor": {
        "roots": ["~/Developer", "~/Clones"]
      }
    }

Leave the key out, and the sweep discovers under every one of `~/Developer`,
`~/Clones`, `~/src`, `~/code` and `~/repos` that exists on this machine. It
combines all of them into one list, instead of stopping at the first one it
finds.

The default list also adds Claude's own scratch-workspace root. On macOS,
that is `~/Library/Application Support/Claude/scratch-workspaces`. On
Windows, that is `%APPDATA%\Claude\scratch-workspaces`. MEASURED on a real
Windows machine: this root holds scratch files today, and no `.git` at all.
Discovery finds nothing under it right now. The root still costs nothing
empty. It is ready the day a scratch workspace does hold a real linked
worktree, the shape the 2026-09-23 incident found on macOS. Linux has no
measured layout here, so nothing is added for it.

When a `janitor.roots` value is not a list of strings, the sweep refuses
discovery. It names the problem, and finds nothing, instead of guessing a
default you did not ask for.

## Single-tier modes

A hook that wants one tier passes `--root PATH` with one mode. `--root PATH`
sweeps the one repository that PATH belongs to. PATH can be a linked worktree
or a folder inside it. The three mode flags exclude each other.

    sweep.py --root PATH --tier1               stale registrations and husks
    sweep.py --root PATH --branches --confirm  branches only
    sweep.py --root PATH --fast --confirm      worktrees already in main only

`--tier1` acts for real and needs no `--confirm`. It prunes stale worktree
registrations and deletes husks. It removes no worktree, reaps no branch, and
stops no process. It runs no process tier.

`--branches` reaps branches that hold no unique work. It previews without
`--confirm`. It removes no worktree and prunes no registration, so every
branch that a worktree checks out stays held. When git gives no worktree
list, it refuses the repository.

`--fast` removes only a worktree whose HEAD is already in the default branch. It
needs a remote-tracking default branch, such as `origin/main`, and refuses the
repository without one. It makes no fetch, no remote read and no branch work, and it
prunes no registration. It keeps the clean, lock, live-session, 1 hour idle and
process keeps, and a tree it cannot prove merged stays. It previews without
`--confirm`.

## What it refuses

The sweep keeps a branch under a protected prefix. `backup/` is the default.

The sweep keeps a branch that any worktree checks out.

The sweep keeps `main`, `master` and the default branch itself.

The sweep keeps a worktree that holds uncommitted or untracked work.

The sweep keeps a worktree that a live session stands in.

The sweep keeps a worktree that holds a lock, and it names the holder. A stale
Claude agent lock does not keep the worktree. The lock forms and the stale test
are in decision `the-janitor-is-one-machine-wide-sweep` (the janitor is one
machine-wide sweep), "A stale agent lock does not keep a worktree".

A stale agent lock frees the worktree for the other checks. `--confirm` then
unlocks and runs `git worktree remove`, never with `--force`. If the removal
fails, the sweep locks the worktree again with the old reason, and the report
says whether that worked. The preview lists the worktree as `REAP` and unlocks
nothing.

The sweep keeps a worktree with a commit that is on no remote branch, and the
reason is `unpushed`. This holds for every worktree, locked or not. A detached
HEAD counts. A repository with no remote keeps every worktree. A failed fetch
adds `: fetch failed` to the reason of a tree kept as `unreadable-subject`. A
SessionEnd run that skipped the fetch inside its 10-minute window adds `: fetch
throttled` instead, and keeps a branch that only a remote-tracking ref proves
safe. It keeps no other tree. The sweep judges other trees on the refs as they stand.

Every `--confirm` run adds two more keeps. A tree that is not merged is kept
until it has been idle long enough, and the reason is `unmerged`. A tree with
git activity inside the idle limit is kept, and the reason is `recently-active`.
A time that cannot be read keeps the tree (`unreadable-subject`). The limits,
and what idle means, are in decision `when-a-worktree-may-be-removed`
(when a worktree may be removed). Strict is the default, so a
job that an older installer wrote is strict with no reinstall. A person passes
`--attended` for the old rules.

An agent worktree is removed at agent end, and by the session-end sweep, under
its own limits. See decision `when-a-worktree-may-be-removed`
(when a worktree may be removed).

The sweep keeps a worktree that any process sits inside, not only a
listener. It names the pids. This check runs right before the removal
itself. On Windows, that is what stops a partial delete: files gone, an
empty folder left, and git still listing the worktree.

The sweep keeps any subject that it cannot read. An unreadable session record,
a `git worktree list` that fails, or a `git status` that fails each mean keep.

## Orphaned TCP listeners

The sweep also finds a TCP listener whose current directory sits inside a
repository or worktree it covers. It signals that listener, by process id
alone, only when every one of these reads a confirmed yes:

- The listener is orphaned. On Linux and macOS, its parent process id is 1.
  On Windows, its parent process is dead. Or a different, newer process now
  holds that same process id.
- No live Claude session has a current directory in the same checkout.
- The listener is owned by the account running the sweep.

An unreadable answer to any one of these means keep. The sweep never turns
"could not tell" into a confident yes.

`--confirm` sends one signal. That is SIGTERM on Linux and macOS. On Windows,
that is `TerminateProcess`. Both go by process id, never by a name or a
pattern. The sweep waits a short grace period. It then reports which
signalled pids are still alive. It never sends a second, stronger signal on
its own.

A single process this sweep cannot read is out of scope. That covers a
process owned by another account, or one that is otherwise access-protected.
The sweep counts it. It never acts on it. It never stops a decision about
anything else because of it.

## Dead-rooted servers

A dead-rooted server is a process whose argv names a script file (`.py`, `.sh`,
`.js`, `.mjs`, `.ts`) that no longer exists. The script's parent directory must
be missing too. The nearest existing ancestor of that
path must carry `.git` or `.claude`. A script missing from a directory that
still exists does not qualify. Such a process is a leftover of a deleted
checkout or worktree. It is often a restart loop that holds no port.

The preview lists each one in a "dead-rooted servers" section, with a reason.
`--confirm` signals one only when both reads answer a confirmed yes:

- The process is orphaned (same read as for a listener).
- The process is owned by the account running the sweep.

An unreadable answer means keep. The signal, the grace period, and the report
are the same as for a listener. This tier is machine-wide and not tied to a
repository, so `janitor.roots` and `.claude/janitor.json` do not narrow it.

## Simulators

A hook records each simulator that a session call booted, in
`<config>/state/sim-boots.jsonl`. The last tier of a full run reads that record.
It judges each recorded device that is `Booted`. A device the record does not
name is never judged, so a simulator you booted yourself stays up.

A device is stopped only when every stop condition holds. Any read that fails
means keep. The conditions are in decision `sweep-shuts-down-idle-simulators`
(the sweep stops idle simulators), ruling 2.

The preview lists each device with `WOULD STOP` or `KEEP` and a reason code.
`--confirm` runs one `xcrun simctl shutdown <UDID>` per device, at most 4 per
run. The rest wait for the next run. There is no `all`, and no erase. With no
`xcrun`, or on Windows, the tier is absent and prints nothing. The tier is
machine-wide, so `janitor.roots` and `.claude/janitor.json` do not narrow it.

The guard reuses the same idle test (`sim_keep_code` in `sweep.py`) to refuse a
boot when an idle twin exists (same decision).

## Loose processes

A loose process is a process whose argv contains the shell-snapshots path
(`.claude/shell-snapshots`). A Claude Code Bash call puts that path in the
argv of its process, and the argv keeps it after the session ends. The match is
a substring, so a command such as `ls` of that directory matches too. The
preview lists each match that is an orphan in a "loose processes" section.
The orphan answer is yes, or unknown when the read fails. A process that is not
an orphan is not listed. This keeps out the wrappers of live sessions, yours
too. A process whose owner cannot be read is counted as unknown.

This tier is report only. `--confirm` stops none of them. A person reads the
list and decides.

## Stale worktree registrations

A registration is stale when git lists a worktree whose directory is gone.
The sweep asks `git worktree prune -n -v` which registrations are stale. The
preview lists each one as `prune WOULD`. `--confirm` then runs
`git worktree prune`, which applies git's own staleness test again. Git alone
decides what is stale. A
locked worktree is never stale. If git gives no answer, the sweep prunes
nothing and says so. This tier runs per repository, so `sweep: false` in
`.claude/janitor.json` opts it out.

## Leftover folders

A leftover folder (a husk) is a real folder directly under
`.claude/worktrees/` that meets all of these:

- Git does not list it as a worktree.
- It is not empty.
- It holds only entries named in `huskNames` in `.claude/janitor.json`, for
  example `["node_modules", ".serve"]`. With no `huskNames`, the sweep finds
  none.

The preview lists each one as `husk WOULD`. A folder with a live session or any
process inside is listed as `husk KEEP`, with the reason. An unreadable folder
or check is KEEP.

`--confirm` deletes each proven husk, after it proves the case again right
before the delete. A folder that changed since the preview is kept. A folder
that became a link is refused, and a link inside a husk is removed as a link.
An error keeps the folder and is reported. The proof rules are in decision
`the-janitor-is-one-machine-wide-sweep` (the janitor is one machine-wide
sweep), "Leftover folders are deleted only when proven twice".

This tier runs per repository, so `sweep: false` opts it out.

## Build folders

At agent end, the SubagentStop reap renames each build folder in the agent's
worktree to a sibling trash name (`<name>.reap-trash-<id>`). A
detached child then deletes the trash. The folders are `native/build`,
`.build` and `DerivedData`, plus each name in `buildDirs` in
`.claude/janitor.json`, for example `["Pods/Build"]`. A name with `/` matches
one path under the worktree root. A bare name matches at any depth. `buildDirs`
adds names and never removes a default.

A folder that fails a check is kept. A `buildDirs` value that is not a list of
strings refuses all build-folder deletes, defaults included. A later reap and
the daily sweep delete trash names a child left. The checks are in decision
`build-dirs-reaped-at-agent-end` (build folders are reaped at agent end).

## How you opt out

Write `.claude/janitor.json` at the root of your repository:

    {
      "sweep": false,
      "protectedPrefixes": ["archive/", "wip/"],
      "huskNames": ["node_modules", ".serve"],
      "buildDirs": ["Pods/Build"]
    }

`sweep` must be the JSON literal `false` to opt out. A string, a number or a
null is not a `false`. The sweep then refuses your whole repository, the same
direction as an unreadable file, not a guess at what you meant.

`protectedPrefixes` is a list of strings. The sweep adds them to `backup/`,
and it never drops the default. A value that is not a list of strings also
refuses your whole repository, instead of silently protecting nothing.

`huskNames` is a list of strings. A value that is not a list of strings also
refuses your whole repository.

`buildDirs` is a list of strings: see "Build folders". A value that is not a
list of strings also refuses your whole repository.

All keys are optional. A file that holds only `protectedPrefixes` stays swept,
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

The tombstone lives 90 days from the reap that wrote its commit. A tombstone
that no log row names lives until you delete it. Until the purge step drops it,
`git gc` cannot take the commits. The purge keeps the younger restore point.

## How you run it every day

Two installers write a scheduled job that runs the sweep with `--confirm`.
Neither one runs that job itself.

`janitor/install_launchd.py` writes a `launchd` `.plist` under
`~/Library/LaunchAgents`, for macOS. It prints the `launchctl load` command
that actually turns the job on.

`janitor/install_schtasks.py` writes a Windows Task Scheduler XML task
definition, under the Claude config directory by default. It prints the
`schtasks /create` command that actually registers the task.

Both installers refuse to run from a linked worktree. When they cannot tell
whether they stand in one, they refuse too. A job generated from a worktree
would name a directory the sweep can remove. Nobody would then notice the
break. Run either installer from your main checkout.

Both installers write a fixed, generic name for the job: never a path, never
a branch. Only one job must exist per machine.

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
