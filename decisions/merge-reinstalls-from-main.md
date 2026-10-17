# Each merge reinstalls from the main checkout

## The ruling

1. The links in `~/.claude` point at one pinned checkout. It is a worktree of the clone that
   holds main's commit on a detached HEAD, and no branch. No lane, review or merge work runs
   in it. The frozen-path guard refuses a file write or a shell write (redirect, `tee`, `sed -i`,
   `cp`, `mv`, `rm`) into the pin and into the stamped worktree the pin link points at. It does
   not read git commands, so `git -C <pin> reset --hard origin/main` is allowed.
2. This repo's `merge.afterMerge` runs `merge/install_from_main.sh` after each merge. The
   script moves the pinned checkout to the new local `main`, then runs the install from it.
   It never installs from the checkout that ran the merge, because that is often a temporary
   worktree.
3. Only that script moves the pinned checkout. A branch switch in any other checkout changes
   no live setting.
4. The install makes the pinned checkout when it is missing. Where the OS refuses symlinks,
   the install copies instead.
5. When the step cannot move or install, it fails loudly. It prints one line that says the
   install did not run and names what to do. It exits non-zero, so the merge tool reports
   FAILED. The merge stays.
6. A plain `settings.json` is backed up before the install replaces it
   (copy-mode-overwrites-no-backup).
7. An install or update never locks a session out. It switches all guard files at once: it
   writes a new stamped folder `hooks/guard.d/<id>/`, then makes one rename of `guard.py`. In
   link mode it makes one rename of the `<clone>-live` link instead. For the guard set this
   replaces the per-file rule of install-hooks-whole.
8. One install runs at a time. One lock file serves every installer path: `install.sh`,
   `install.ps1` and the post-merge hook that `install.ps1` writes.
9. Each installer path logs a start line and an end line. Each line carries a unique install
   id and the pid.

Reason: a merge that adds a file must reach `~/.claude` with no hand install. Links to the clone
itself would follow its checked-out lane branch, so unreviewed hooks would go live.

Kind: build
Plan: decisions/merge-reinstalls-from-main.md#the-ruling (all)
Home: merge/install_from_main.sh

## Holes, named

Debts: `pin-switch-in-place-mix`, `live-pin-first-move-gap`, `install-lock-stale-by-age`,
`install-lock-trap-no-id`, `install-early-exit-unlogged`, `guard-old-install-mixes-once`,
`guard-realpath-after-flip`.

## Named limits

- When the local main does not move, the install runs from the old main. The merge tool reports the failed move.
- A merge run from a worktree made before this change cannot find the script. The merge tool reports FAILED, and the merge stays.
