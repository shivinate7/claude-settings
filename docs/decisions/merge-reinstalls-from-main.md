# Each merge reinstalls from the main checkout

## The ruling

1. The links in `~/.claude` point at one pinned checkout. It is a worktree of the clone that holds main's commit on a detached HEAD,
   and no branch. No lane, review or merge work runs in it. The frozen-path guard refuses a file write or a shell write (redirect,
   `tee`, `sed -i`, `cp`, `mv`, `rm`) into the pin and into the stamped worktree the pin link points at. It does not read git
   commands, so `git -C <pin> reset --hard origin/main` is allowed.
2. This repo's `merge.afterMerge` runs `merge/install_from_main.sh` after each merge. The script moves the pinned checkout to the
   new local `main`, then runs the install from it. It never installs from the checkout that ran the merge, because that is often
   a temporary worktree.
3. The move never exposes a mix (owner ruling 2026-10-15). The new main is checked out in a fresh worktree `<clone>-live-<commit>`, and `<clone>-live` becomes a link to it by one rename. The old worktree stays until the next move. Without link rights the pin is switched in place. The script takes the install lock the installers take (`install-hooks-whole`), reads main's commit only once it holds the lock, and holds the lock through the install.
4. Only that script moves the pinned checkout. A branch switch in any other checkout changes no live setting.
5. The install makes the pinned checkout when it is missing. Where the OS refuses symlinks, the install copies instead.
6. When the step cannot move or install, it fails loudly. It prints one line that says the install did not run and names what to
   do. It exits non-zero, so the merge tool reports FAILED. The merge stays. A merge run from a worktree made before this
   change cannot find the script, so the tool reports FAILED. When the local main does not move, the install runs from the old
   main and the tool reports the failed move and exits non-zero (owner ruling, undated).

Reason: a merge that adds a file must reach `~/.claude` with no hand install. Links to the clone itself would follow its
checked-out lane branch, so unreviewed hooks would go live.

Kind: build
Plan: docs/decisions/merge-reinstalls-from-main.md#the-ruling (all)
Home: merge/install_from_main.sh
