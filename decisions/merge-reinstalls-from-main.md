# Each merge reinstalls from the main checkout

## The question

`install.sh` links the shipped skills, hooks and tools into `~/.claude`. A merge that adds a
file does not reach `~/.claude` until someone runs the install again. How does each merge
keep `~/.claude` current?

## The ruling

Owner, 2026-10-11:

1. This repo's `merge.afterMerge` runs `merge/install_from_main.sh` after each merge.
2. The script finds the checkout that holds the `main` branch and runs its `install.sh`. It
   never installs from the checkout that ran the merge, because that is often a temporary
   worktree.
3. When no checkout holds `main`, the step fails loudly. It prints one line that says the
   install did not run and names what to do. It exits non-zero, so the merge tool reports
   FAILED. The merge stays.
4. A plain `settings.json` is backed up before the install replaces it. See decision
   copy-mode-overwrites-no-backup.

## The incident

2026-10-11: after the merges of #321 to #325, the skills `design-review` and `impeccable`
and the hook `sim_boot_record.py` were missing from `~/.claude`. They came in only when the
install ran again by hand.

## Named limits

- When the local main does not move, the install runs from the old main. The merge tool
  already reports the failed move.
- A merge run from a worktree made before this change cannot find the script. The merge
  tool reports the step as FAILED, and the merge stays.
- Windows: the script prints a pointer to `install.ps1` and exits 0.
