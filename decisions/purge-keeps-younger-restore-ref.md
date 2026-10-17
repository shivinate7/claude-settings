# The purge keeps the younger restore ref

## The ruling

The restore ref is `refs/janitor/reaped/<branch>`. The sweep writes it at the branch tip before each
delete. Each reap overwrites it. The purge drops a restore ref only when both hold:

- The ref still holds the expired entry's commit.
- No unexpired entry names the same repo, branch and commit.

Only a git exit 1 with empty stderr reads as "ref gone". Any other failure keeps the ref and reports an error.

The restore point is the branch tip only. The sweep saves no snapshot of dirty content. The restore log
is not compacted. The sweep does not reap dirty trees (janitor-dirty-test-stays).

Reason: `purge_tombstones` dropped the ref by name when an old entry expired, so a branch reaped twice
lost its younger restore point. Which branches reach the log is set by
`a-branch-is-redundant-by-patch-not-by-ancestry`. What an unattended sweep may stop or remove is set by
`unattended-sweep-stops-proven-orphans`.

Protection: `janitor/test_sweep.py` purge cases, including
`test_an_expired_entry_keeps_the_ref_that_holds_the_younger_commit` and
`test_a_reap_landing_after_the_read_keeps_the_younger_ref`. `janitor/mutate_sweep.py` has mutant rows for
the purge ref rule.

Kind: process
Home: janitor/sweep.py

## Holes, named

Unverified: `realpath` on mapped or `subst` drives; stderr text on other git versions; older Python
versions, for `realpath` errors.
