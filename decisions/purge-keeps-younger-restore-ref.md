# The purge keeps the younger restore ref

## The question

When a branch name is reaped twice, which restore ref must the purge keep?

The restore ref is `refs/janitor/reaped/<branch>`. The sweep writes it at the branch tip before each delete. Each reap overwrites it.

## The ruling

The purge drops a restore ref only when both hold:

- The ref still holds the expired entry's commit.
- No unexpired entry names the same repo, branch and commit.

Only a git exit 1 with empty stderr reads as "ref gone". Any other failure keeps the ref and reports an error.

The restore point is the branch tip only. The sweep saves no snapshot of dirty content. The restore log is not compacted.

Owner word, 2026-10-13 12:33 CDT: fix the bug, save only the branch tip, no snapshot of dirty content, no log compaction.

Closed, by owner word 2026-10-13 15:56 CDT (option A): the sweep does not reap dirty trees. See janitor-dirty-test-stays (the janitor's dirty test stays as it is). The junk-file list is not needed now.

## Why

Measured incident. `purge_tombstones` dropped `refs/janitor/reaped/<branch>` by name when an old entry expired. A branch reaped twice then lost its younger restore point.

- The real log holds 4803 rows over 5 repos.
- 37 of 39 re-reaped branches were reaped at the same tip.
- First possible loss: about 2026-12-22. No row had expired yet.

Which branches reach the log is set by `a-branch-is-redundant-by-patch-not-by-ancestry`, the patch-id test for a redundant branch. This record covers only the restore ref kept after a reap. What an unattended sweep may stop or remove is set by `unattended-sweep-stops-proven-orphans`.

## What protects it

- `janitor/test_sweep.py`, purge cases. These include `test_an_expired_entry_keeps_the_ref_that_holds_the_younger_commit` and `test_a_reap_landing_after_the_read_keeps_the_younger_ref`.
- `janitor/mutate_sweep.py`, mutant rows for the purge ref rule.

## Review rounds

- Round 1 passed.
- Round 2 found no blocker and 3 holes. All 3 were fixed.
- Round 3 passed with no blocker.
- All rounds ran on Sonnet.

## Holes, named

Debts: `purge-key-case-folds` (branch names compare with exact case), `purge-bad-row-key-raises` (a list or dict key stops the purge), `purge-git-trace-missing-ref` (a missing ref reads as an error while git tracing is on), `purge-snapshot-race` (unexpired rows are read once, at purge start), `purge-realpath-per-row` (realpath runs once per unexpired row), `purge-update-ref-mutant-missing` (no mutant drops only the commit argument of `update-ref -d`), `purge-confirm-total-wrong` (the confirm total counts kept refs), `purge-orphan-ref-kept` (a ref no log entry names is kept forever).

## Unverified

- `realpath` on mapped or `subst` drives.
- Stderr text on other git versions.
- Older Python versions, for `realpath` errors.

Kind: process
Home: janitor/sweep.py
