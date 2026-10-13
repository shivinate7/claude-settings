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

Open and separate: whether the sweep may reap dirty trees. That question needs the owner's list of junk files first.

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

Each hole ships under the three-round review cap. "Fix: not named" means that no fix is recorded yet.

- **Case folds.** Cause: branch names compare with exact case, but NTFS ref names fold case. Effect: an expired `Foo` row and an unexpired `foo` row at one commit drop the shared ref. Main dropped it too. The real log has 0 case collisions. Fix: lower-case the branch in the key.
- **Bad row key.** Cause: a log row with a list or dict `branch` or `commit` and a live `time_ms` raises TypeError. `realpath` has no try block. Effect: `--purge` stops, preview included, until that row is 90 days old. Main kept such a row as unreadable. Nothing in the repo writes such a row. Fix: guard the key build.
- **Git trace output.** Cause: with `GIT_TRACE=1` or `GIT_TRACE2=1` set, git writes to stderr on a missing ref. Effect: the missing ref reads as an error while the variable is set. The ref and its row stay. Checked on git 2.55.0.windows.3 only. Fix: not named.
- **Snapshot race.** Cause: the set of unexpired rows is read once, at purge start. Effect: a reap that logs the same commit later is not seen. The old-value pin on `update-ref -d` still protects a changed ref value. Read from code, not run. Fix: not named.
- **Realpath cost.** Cause: `realpath` runs once per unexpired row, in preview too. Effect: a dry run on a copy of the real log took 1.35 s, against 0.015 s before. A first call to an unreachable network host took 1.15 s. Fix: build the key lazily, or cache it per repo string.
- **Missing mutant.** Cause: the harness has no mutant that drops only the commit argument of `update-ref -d`. Effect: the harness alone does not catch it. A hand run of that change was killed by `test_a_reap_landing_after_the_read_keeps_the_younger_ref`. Unverified: the row "the ref is dropped by branch name" in `janitor/mutate_sweep.py` may drop that argument, with a different named killer. Fix: add one mutant row.
- **Confirm total.** Cause: the "purge: N" total in the confirm report counts rows whose ref was kept. Effect: the total counts more than the refs dropped. Fix: not named.
- **Orphan ref kept.** Cause: the purge keeps a ref when no log entry names its commit. Effect: such a ref is kept forever. The old code dropped it at 90 days. Fix: not named.

## Unverified

- `realpath` on mapped or `subst` drives.
- Stderr text on other git versions.
- Older Python versions, for `realpath` errors.

Kind: process
Home: janitor/sweep.py
