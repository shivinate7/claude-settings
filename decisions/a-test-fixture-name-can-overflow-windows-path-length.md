# A fixture name built from a test's own description can overflow Windows path length

## The claim

Git names its own worktree admin directory after the worktree's own basename. A worktree path
built from a test method's full, sentence-length name can push that admin path past Windows'
path-length ceiling. `git worktree add` then fails with a real `git` error, not a suite bug.

## The measurement

`janitor/test_sweep.py`'s `PrimaryCheckoutExclusionTests.setUp` built its linked worktree's
path as `primary-checkout-linked-<full test method name>`, and this suite's method names are
full, readable sentences. On a real Windows machine, the fixture's own `git worktree add`
failed at setup:

```
fatal: could not create directory of
'.git/worktrees/primary-checkout-linked-test_no_decision_is_recorded_against_the_primary_
checkout_when_swept_via_a_linked_worktree': Filename too long
```

The identical fixture shape, run against the same three test methods, passes on POSIX. Its
path-length limits are far looser. This is a genuine platform difference, not a flake.

## Why the fixture, not `janitor/sweep.py`

No production code in this repository builds a worktree's directory name from a test's own
description, or from any other long, free-form string. `sweep.py` never names a worktree at
all. It only reads worktree paths git already created. The defect is confined to this one
fixture's own naming choice.

## The fix

`PrimaryCheckoutExclusionTests.setUp` now derives its directory tag from
`hashlib.md5(self.id().encode("utf-8")).hexdigest()[:12]`, a short, deterministic string, in
place of the full test method name. The fixture's own `require` calls also now include the
real git stderr in their failure message. The earlier version discarded it. The first
diagnosis of this defect needed a second, separate reproduction to recover the actual error
git printed.

## What this decision is, and is not

This does not audit every fixture in the repository for the same naming pattern. It fixes the
one class this build measured the failure against.
