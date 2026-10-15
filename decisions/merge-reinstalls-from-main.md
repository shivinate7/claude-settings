# Each merge reinstalls from the main checkout

## The question

The install links the shipped skills, hooks and tools into `~/.claude`. A merge that adds a
file does not reach `~/.claude` until someone runs the install again. How does each merge
keep `~/.claude` current, and which checkout do the links point at?

## The ruling

Owner, 2026-10-11, and owner, 2026-10-15 (the pinned checkout):

1. The links in `~/.claude` point at one pinned checkout. It is a worktree of the clone that
   holds main's commit on a detached HEAD, and no branch. No lane, review or merge work runs
   in it.
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

Kind: build

## The incidents

- 2026-10-11: after the merges of #321 to #325, the skills `design-review` and `impeccable`
  and the hook `sim_boot_record.py` were missing from `~/.claude`. They came in only when the
  install ran again by hand.
- 2026-10-15: Windows Developer Mode made symlinks work on the owner's machine. Links to the
  clone itself would follow its checked-out branch. That clone was on a lane branch the same
  day, so its unreviewed hooks would have gone live for every session.

## Named limits

- When the local main does not move, the install runs from the old main. The merge tool
  already reports the failed move.
- A merge run from a worktree made before this change cannot find the script. The merge
  tool reports the step as FAILED, and the merge stays.
