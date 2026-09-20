# Build plan: the machine-wide janitor

This plan covers work in this repository only. It says what the parent level
builds, and what it leaves to a child repository such as Banchi.

The owner decided every choice below on 2026-09-20. This plan names the cost of
each one. A later reader can then judge the argument, and not only the answer.

## What this builds

A re-runnable sweep. It reaps local branches that hold no unique work, and
it removes git worktrees that no session still uses. It runs across every
repository on this machine. It refuses to reap anything that holds the only
copy of its work.

## The cause this fixes

Banchi's sweep keeps a branch only when git says the branch is an ancestor of
the default branch. A rebase or a cherry-pick changes the commit ids, so that
test goes false while the same patch sits on the default branch. The sweep then holds
that branch for ever.

`git cherry` compares patch ids, not commit ids, so it sees through a rebase. A
commit already on the base prints `-`. A new commit prints `+`.

The new keep rule uses both tests. A branch is reapable when it is an ancestor
of the base, OR when `git cherry` prints no `+`. The sweep keeps it, and names it as the
only copy, when a `+` survives and no remote carries it.

The safe direction holds. A commit that changed during a rebase prints `+`, so
the sweep keeps it. A false `-` needs two identical patches, which means that the
content really sits on the base.

## The measurements

Taken on this machine on 2026-09-20, across the five repositories under
`~/Developer`.

| Subject | Count |
| --- | --- |
| Local branches | 98 |
| Already an ancestor of the default branch | 46 |
| Redundant by patch id, but not an ancestor | 5 |
| Genuinely unmerged | 42 |
| Unmerged and on no remote, the only copy | 6 |
| Registered worktrees | 50 |
| Worktrees under `.claude/worktrees/` | 43 |
| Worktrees that are dirty | 10 |
| Worktrees that are locked | 8 |
| Worktrees a live session stands in | 6 |
| Husk directories | 0 |
| Redundant by a squash merge | 0 |

The ancestry test reaps 46 branches. The patch test adds 5 more.

This table counts content, and nothing else. It asks one question of each
branch: does the branch hold work that sits nowhere else? The sweep asks a
second question first. It applies the refusals in order. A branch that a
worktree checks out therefore lands in the checked-out group. It never reaches
the ancestor group.

Both numbers are right, and they answer different questions. A review on
2026-09-20 re-measured both, and the arithmetic ties them together. Of the 46
ancestors, 29 sit in a worktree today. 46 minus 29 leaves the 17 that the
sweep's own preview reports. The
squash test adds none today, so this build does not ship it.

## The decisions

**The code lands in a new `janitor/` directory.** The directory joins
`landed-dirs.txt` and `CONFIG_FROZEN_DIRS` in `hooks/guard.py` in the same
change. `lint/check_landed_dirs.py` then holds the two in agreement. A session must
not rewrite a program that deletes branches. The frozen claim is therefore the
reason to do this, and not the cost of it.

**The sweep is automatic, and a repository opts out.** The sweep visits every
repository that carries no opt-out file. The owner accepted this cost. Take a
repository where long-lived local branches are normal work. It loses them on
the first sweep, unless somebody adds the file first. The tombstone below makes
that loss recoverable.

**The opt-out file is `.claude/janitor.json`, inside the repository.** It holds
two optional keys. `"sweep": false` opts the whole repository out.
`"protectedPrefixes"` names more branch prefixes to protect, beside the default
`backup/`. A file that holds only `protectedPrefixes` stays swept, and protects
more names. An absent file means swept, which is the auto-on default.

Three constraints pick this name. The file travels with a clone, so it does not
sit in `.git/`. The sweep reads it as data, and never runs it. It carries more
than a yes or a no, so a bare marker file cannot do the job.

The
repository that pays the cost holds its own consent. The file travels with a
clone. The sweep reads the file as data. The sweep never runs code that a
repository supplies. A repository that supplies code to a frozen tool can do
everything that tool can do.

**Two triggers.** A `SessionEnd` hook sweeps only the repository whose session
ended. A daily launchd agent sweeps every repository. The hook always
fails open, because a hook that can refuse the end of a session is worse than
a leak. The installer writes the launchd plist into `~/Library`. Nobody commits it, and
the installer refuses to run from a linked worktree.

**Every reaped branch leaves a tombstone.** The sweep writes
`refs/janitor/reaped/<branch>` at the tip before it deletes the branch. It also
appends one line to a restore log: repository, branch, commit id, time. The
commits stay reachable, so `git gc` can never take them. A later purge step
drops a tombstone after 90 days.

The 90 comes from git itself, and not from a fresh guess. Git expires an
unreachable reflog entry after 30 days, and it prunes a loose object after two
weeks. A tombstone under 30 days buys nothing. The reflog already gives that
much. Git keeps a reachable reflog entry for 90 days, so 90 is a number this
machine already uses. It also covers a long absence.

The purge reads the age from the restore log's own timestamp, and never from
the mtime of the ref. An mtime changes for reasons that have nothing to do with
the reap.

**Worktree removal is automatic too.** The refusals decide, not a name list.

**The parent ships the generic sweep only.** Branches and worktrees are pure
git plus a liveness oracle, so they transfer to any repository. A process tier and a
service teardown do not transfer: that code names one repository's own files.
A child repository keeps its own tier, and this repository ships the guide for
writing one.

## The refusals

No refusal here can weaken. Each one gets a test arm that violates it.

1. The sweep never considers a branch under a protected prefix. `backup/` is the
   default. A repository adds more prefixes in its opt-out file.
2. The sweep never deletes a branch that any worktree checks out.
3. The sweep never removes a worktree that holds uncommitted or untracked work.
4. The sweep never removes a worktree that a live session stands in.
5. A locked worktree names its holder, and the sweep leaves it alone.
6. The sweep never cuts `main`, `master` or `HEAD`.
7. The sweep keeps a subject that it cannot read. An unreadable session record, a
   `git worktree list` that fails, or a `git status` that fails each mean keep.

Liveness comes from `~/.claude/sessions/*.json`. A record counts as live only
when the id is alive AND the recorded start time still matches. A recycled id
then cannot inherit a dead session's claim. The oracle compares the start time
as epoch milliseconds.

A rendered clock time carries a timezone, and that form of the test fails. The measurement for this plan hit exactly that trap. A
five-hour offset looked like a match.

## The phases

### Phase 0: close the hole in the guard

Measured against the live hook, `hooks/guard.py` refuses `pkill`, `git stash`,
`git reset` and `git restore`. It allows `git branch -D`,
`git worktree remove` and `git worktree prune`. Six worktrees on this machine
hold a live session right now, and nothing stops a session from deleting one.

Add the three forms to the shared-tree refusal. Give the sweep the one
exception, and point the exception at the constant the sweep emits, never at a
copy of its name.

Check: a new arm in `hooks/mutate_guard.py` survives today and dies after the
fix. This phase lands as its own pull request, before the sweep.

### Phase 1: the sweep

Build `janitor/sweep.py`. It takes one or more repository roots, or it
discovers them. It sweeps each repository against that repository's own default
branch.

Resolve the default branch in this order: `origin/HEAD`, then local `main`,
then local `master`. If none answers, refuse the repository out loud and reap
nothing there. One repository on this machine, `sillage`, has an unset
`origin/HEAD` with an `origin` remote present, so the fallback runs on day one.

Preview is the default output, and it names every decision with its reason.
`--confirm` is required before the sweep deletes anything. The sweep computes the allow or refuse
decision from what a branch or a tree IS. The sweep never matches a
name against a list of guessed names.

The sweep never stops a running program, and never touches a remote.

### Phase 2: the proof

Write `janitor/test_sweep.py` in the style this repository already uses: a
plain `python3` file with `unittest`, which builds throwaway repositories in a
temporary directory. Wire it into `.github/workflows/gates.yml` as its own
named step.

The anchor arm is the rebase ghost. It must go red against a keep rule that
tests ancestry alone. A suite that passes against an ancestry-only sweep
proves nothing that this build exists for.

Every arm asserts that its subject set is not empty before it asserts a
verdict. An arm that passes over an empty set proves nothing. That failure
happened three times in the Banchi work.

Each refusal above gets an arm that violates it. The liveness arm holds a
record whose stored start time does not match the live id. That arm must read
the session as dead.

Mutate each assertion and show that it fails.

### Phase 3: the records and the guide

Write one decision entry per argument above, as a slug. Claim the numbers at
merge. Add a row to `lint/rule_mechanisms.json` for every new rule, or an
argued `unmechanized` row.

Write `janitor/GUIDE.md` for a child repository. It states the opt-out file
format, the protected prefixes, and how a repository writes its own
repository-specific tier and runs the generic sweep first.

## What this plan does not do

It does not change what the sweep refuses to reap. It widens what the sweep can
prove redundant. Any new refusal is a decision to raise, not one to make.

It does not touch `~/Developer/pkmnscan`. Removing that repository's own tier 2
is a later step, and the owner names it.

It does not port the process tier, and it does not port the service teardown.

It does not ship the squash test. A squash merge leaves one new patch id, so
`git cherry` still prints `+`. The known fix builds a synthetic commit with
`git commit-tree <branch tree> -p <merge base>` and runs `git cherry` against
that. This machine holds no branch of that shape today, so the rule would ship
untested against real work. Phase 2 carries a fixture that proves the gap
exists, so the record holds the gap, and nobody forgets it.
