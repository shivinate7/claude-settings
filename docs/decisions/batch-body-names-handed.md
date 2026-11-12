# An integration PR body names each handed lane

## The ruling

Owner, 2026-11-08 11:57 CST, typed in degen lane session_013NEJKzoN2eD5oih2K39Be8, answering where the lane-drop guard goes: "2. it would go in claude-settings".

The merge tool as the home, and the refusal at the merge confirm as well as at the draft step, are this lane's design. They come from the degen lane's suggestion, relayed by the coordinator. They are not the owner's words. A PR marked ready by hand skips the draft step, so the merge confirm checks again.

The guard refuses the merge when a lane PR handed for the batch is not named in the integration PR body as merged or held, with a reason.

The roadmap step that builds it is `runner-drops-handed-lane` (order 768).

Before an integration PR goes ready, its body names every handed lane. A lane is named in one of two ways:

- Merged: on the `Lanes:` line, when it is in the batch.
- Held: on a left-out line with a reason, when it is not.

The draft step and a ready `merge <pr> --confirm` refuse a handed PR that the body does not name.

## The mistake and the harm

Degen PR #438 (the milestone-ui split lane) was handed to the batch runner. Batch 9's integration PR, #459, left it out. Its body did not name it, and no word came. It never reached main.

The mistake: the batch body was written by hand, and nothing checked it against the handed lanes.

The harm: a reviewed lane was lost without a word.

## The rule

- A handed lane is an open lane PR on the integration PR's base. Its newest review record reads done. The base does not hold its head yet.
- An integration PR has a `Lanes:` line in its body, or its head holds the head of a handed lane. A lone lane is not an integration PR. This check skips it and says nothing.
- Each handed lane is either merged or held. Merged: it is on `Lanes:`, and the integration head holds its head. Held: it is on a left-out line with a reason.

## The body grammar

- `Lanes: #n #m` lists the batch's lane PRs. The line may carry a bullet or bold, in any case.
- A left-out line starts the line with `Dropped`, `Held` or `Next batch`, in that case. Its label ends at its first colon outside parentheses. Only the numbers after that colon count. Each number needs a reason: a `(...)` right after it, or a `(...)` in the label before the colon.
  - `Dropped (macOS CI red): #n #m` passes.
  - `Dropped from #n: #m (macOS CI red)` passes.
  - `Dropped earlier: #n` fails. It has no reason.
- A late lane is one done after the batch was built. It is not exempt. It goes on `Next batch (late): #n`.

## Verdicts

Each refusal names every PR it finds, one line each. It stops the run.

1. A handed PR is in the batch but not on `Lanes:`.
2. A handed PR is not in the batch and is on no left-out line.
3. A PR is on a left-out line with no reason.
4. A PR is on `Lanes:`, and the integration head does not hold its head.
5. A failed read stops the run. Unknown is never a pass. With no `Lanes:` line, `--undo-check-unknown-ok "<reason>"` lifts a failed lane read, as it does for the dropped-lane check.
6. Every handed lane is named. One line prints: `merge: handed-lane check: N lanes in the batch, M named as left out.`

## The one departure

Departs from: the batch bodies so far, which took a left-out line with no reason. Such a line now refuses. Claude-settings PR #2046's body has `Dropped earlier: #1552 ...` with no reason. That line is the case that changes.

## Where it runs

- `merge/merge.py` runs the check on three paths:
  - The draft step: `merge <pr> --confirm` on a draft PR. It runs first, before the records page rebuild, the push and the ready mark.
  - `merge <pr> --confirm` on a ready PR. It runs before the lock is taken.
  - The preview: `merge <pr>` with no `--confirm`. It prints BLOCKED when the check refuses.
- A refusal pushes nothing and merges nothing. A draft stays a draft.
- It reads with the merge tool's own review-record read (`reviewed_read`) and head compare (`holds_head`). It adds no second reader.

## Cost

- Per run with a `Lanes:` line: each preview, each draft step and each ready `--confirm`. The review-record read costs 2 list reads, and 3 gh calls per ready PR with a record.
- Each compare is one `gh api` call. Against the base: one per open PR on the base that reads done, other than the integration PR. Against the integration head: one per handed PR, and one per Lanes-named open PR not in the batch. A handed PR named on `Lanes:` but not in the head is compared twice.
- A body with no `Lanes:` line: one `git log` in the worktree, then two `git` processes per lane tip not on the base. No gh call.
- No long-lived process, no file and no timer.

## Status

Built on all three paths in `merge/merge.py`. The roadmap step `runner-drops-handed-lane` is the build. Its refusals cite this decision.

Kind: process
Home: merge/merge.py
