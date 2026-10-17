# Prune cases skip when this account cannot make a real symlink

## The ruling

A Windows account without Developer Mode holds no `SeCreateSymbolicLinkPrivilege`, so `ln -s` writes a
copy. `install.sh` already falls back to a copy for this case. The cases prune1, prune3 and prune5 in
`hooks/test_install_src.sh` assert real-symlink behavior that this state cannot produce.

- The suite probes once, before any case runs. It makes a link in a scratch directory, then checks
  `[ -L ]` on the result. The outcome sets `SYMLINK_CAPABLE`. This is a capability probe, not a
  platform-name check, so any account that holds the privilege still runs the three cases for real.
- prune1, prune3 and prune5 return early with a `skip` call when the probe finds no privilege. No
  assertion in them changes.
- A skip stays visible. The `SKIP` counter and the `skip` function print `SKIP -`, distinct from `ok`
  and `FAIL`. The tally line reads `N passed, M failed, K skipped`.

Reason: Windows CI failed these three cases on platform state alone, not on a defect in `install.sh`.
The same skip shape appears in `hooks/test_guard.py` (`subject_unread_log_case`), `hooks/mutate_guard.py`
(`only_on`) and `install.ps1`.

Kind: build
Plan: decisions/prune-cases-skip-without-symlink-privilege.md#the-ruling (windows)
Home: hooks/test_install_src.sh

## Holes, named

The probe and the early-return guard are proven only on the negative branch.
