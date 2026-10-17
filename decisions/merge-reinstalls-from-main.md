# Each merge reinstalls from the main checkout

## The question

The install links the shipped skills, hooks and tools into `~/.claude`. A merge that adds a
file does not reach `~/.claude` until someone runs the install again. How does each merge
keep `~/.claude` current, which checkout do the links point at, and how does an install switch
files without locking sessions out?

## The ruling

Owner, 2026-10-11, owner, 2026-10-15 (the pinned checkout), and owner, 2026-10-15 17:40 CDT
(the install switch):

1. The links in `~/.claude` point at one pinned checkout. It is a worktree of the clone that
   holds main's commit on a detached HEAD, and no branch. No lane, review or merge work runs
   in it. The frozen-path guard enforces part of this (owner, 2026-10-17 11:40 CDT): it refuses
   a file write or a shell write (redirect, `tee`, `sed -i`, `cp`, `mv`, `rm`) into the pin and
   into the stamped worktree the pin link points at. It does not read git commands, so
   `git -C <pin> reset --hard origin/main` is allowed.
2. This repo's `merge.afterMerge` runs `merge/install_from_main.sh` after each merge. The
   script moves the pinned checkout to the new local `main`, then runs the install from it.
   It never installs from the checkout that ran the merge, because that is often a temporary
   worktree.
3. Only that script moves the pinned checkout. A branch switch in any other checkout changes
   no live setting.
4. The install makes the pinned checkout when it is missing. Where the OS refuses symlinks,
   the install copies instead, as before.
5. When the step cannot move or install, it fails loudly. It prints one line that says the
   install did not run and names what to do. It exits non-zero, so the merge tool reports
   FAILED. The merge stays.
6. A plain `settings.json` is backed up before the install replaces it. See decision
   copy-mode-overwrites-no-backup.
7. An install or update never locks a session out. It switches all guard files at once: it
   writes a new stamped folder `hooks/guard.d/<id>/`, then makes one rename of `guard.py`. In
   link mode it makes one rename of the `<clone>-live` link instead. This replaces, for the
   guard set, the per-file rule of install-hooks-whole (an install never shows a session a
   half-copied hook). It is the install's answer to the 2026-10-14 incident there.
8. One install runs at a time. One lock file serves every installer path: `install.sh`,
   `install.ps1` and the post-merge hook that `install.ps1` writes.
9. Each installer path logs a start line and an end line. Each line carries a unique install
   id and the pid.

Kind: build
Plan: decisions/merge-reinstalls-from-main.md#the-ruling (all)
Home: merge/install_from_main.sh

## The incidents

- 2026-10-11: after the merges of #321 to #325, the skills `design-review` and `impeccable`
  and the hook `sim_boot_record.py` were missing from `~/.claude`. They came in only when the
  install ran again by hand.
- 2026-10-15: Windows Developer Mode made symlinks work on the owner's machine. Links to the
  clone itself would follow its checked-out branch. That clone was on a lane branch the same
  day, so its unreviewed hooks would have gone live for every session.

## Holes, named

Debts: `pin-switch-in-place-mix` (without symlink rights, the pin move switches in place and a
reader can see a mix), `live-pin-first-move-gap` (the first move from a plain directory leaves
`<clone>-live` absent for
milliseconds), `install-lock-stale-by-age` (the lock is stale by age only; a stale lock that
cannot be removed loops with no timeout, two waiters can both take it, and a live run past 10
minutes can overlap a second install), `install-lock-trap-no-id` (the EXIT trap removes the lock
with no id check, so a run that outlives the stale age can remove a later holder's lock),
`install-early-exit-unlogged` (refusals and lock timeouts exit before the start line, so they log
nothing), `guard-old-install-mixes-once` (a guard install made before this rule mixes
once, until the first install under it), `guard-realpath-after-flip` (in link mode,
`realpath(__file__)` can run after a link flip, so guard.py and its modules can come from two
main commits for milliseconds).

## Named limits

- When the local main does not move, the install runs from the old main. The merge tool
  already reports the failed move.
- A merge run from a worktree made before this change cannot find the script. The merge
  tool reports the step as FAILED, and the merge stays.
