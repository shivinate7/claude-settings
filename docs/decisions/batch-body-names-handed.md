# An integration PR body names each handed lane

## The ruling

The roadmap step that adds this check (`runner-drops-handed-lane`, order 768) sets the rule. No owner ruling is on file for it.

Before an integration PR goes ready, its body names every handed lane. A lane is named in one of two ways:

- On the `Lanes:` line, when it is in the batch.
- On a left-out line with a reason, when it is not.

The draft step refuses a handed PR that the body does not name.

## The mistake and the harm

Degen PR #438 (the milestone-ui split lane) was handed to the batch runner. Batch 9's integration PR, #459, left it out. Its body did not name it, and no word came. It never reached main.

The mistake: the batch body was written by hand, and nothing checked it against the handed lanes.

The harm: a reviewed lane was lost without a word.

## The rule

- A handed lane is an open lane PR on the integration PR's base. Its newest review record reads done. The base does not hold its head yet.
- An integration PR has a `Lanes:` line in its body, or its head holds the head of a handed lane. A lone lane is not an integration PR. This check skips it and says nothing.
- Each handed lane is either in the batch or left out. In the batch, it is on `Lanes:`, and the integration head holds its head. Left out, it is on a left-out line with a reason.

## The body grammar

- `Lanes: #n #m` lists the batch's lane PRs.
- A left-out line starts with `Dropped`, `Held` or `Next batch`. Only the numbers after the first colon count. Each number needs a reason: a `(...)` right after it, or a `(...)` in the label before the colon.
  - `Dropped (macOS CI red): #n #m` passes.
  - `Dropped from #n: #m (macOS CI red)` passes.
  - `Dropped earlier: #n` fails. It has no reason.
- A late lane is one done after the batch was built. It is not exempt. It goes on `Next batch (late): #n`.

## Verdicts

Each refusal names every PR it finds, one line each. It stops the draft step.

1. A handed PR is in the batch but not on `Lanes:`.
2. A handed PR is not in the batch and is on no left-out line.
3. A PR is on a left-out line with no reason.
4. A PR is on `Lanes:`, and the integration head does not hold its head.
5. A failed read stops the step. Unknown is never a pass.
6. Every handed lane is named. One line prints: `merge: handed-lane check: N lanes in the batch, M named as left out.`

## The one departure

Departs from: the batch bodies so far, which took a left-out line with no reason. Such a line now refuses. `Dropped earlier: #n`, used in claude-settings PR #2046, is the case that changes.

## Where it runs

- `merge/merge.py`, `draft_step`: the path that `merge <pr> --confirm` takes on a draft PR.
- It runs first. That is before the records page rebuild, the push and the ready mark. A refusal pushes nothing, and the PR stays a draft.
- It reads with the merge tool's own review-record read (`reviewed_read`) and head compare (`holds_head`). It adds no second reader.

## Cost

- Per draft step only. The review-record read costs 2 list reads, and 3 gh calls per ready PR with a record. Then one compare per handed PR against the integration head, and one against the base.
- Process starts: none. Files written: none. Timers: none.

## Status

Not built. The roadmap step `runner-drops-handed-lane` builds it. Its refusals cite this decision.

Kind: process
Home: merge/merge.py
