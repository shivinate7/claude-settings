# An integration PR body names each handed lane

## The ruling

Owner, 2026-11-08 11:57 CST, typed in the degen lane, session_013NEJKzoN2eD5oih2K39Be8, answering where the lane-drop guard goes: "2. it would go in claude-settings".

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

- A handed lane is an open lane PR on the integration PR's base. Its newest review log reads done. The base does not hold its head yet.
- Every batch is checked, lone lanes included. A lone lane is its own integration PR, so its body is checked for handed lanes like any batch's.
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
  - The draft step: `merge <pr> --confirm` on a draft PR. It runs first, before the records page rebuild, the push and the ready mark. It takes no lock. A PR that turns draft after the lock is taken runs it under that lock.
  - `merge <pr> --confirm` on a ready PR. `handed_check` runs before the lock is taken. `handed_local` runs after it, under the lock, before any claim or push to the branch.
  - The preview: `merge <pr>` with no `--confirm`. It takes no lock. It prints BLOCKED when the check refuses.
- A refusal pushes no branch and merges nothing. A draft stays a draft.
- A refusal from `handed_local` on a ready PR still takes and frees the merge lock: one push and one delete of its ref on origin.
- `handed_check` reads with the merge tool's own review-log read (`reviewed_read`) and head compare (`holds_head`). `handed_local` reads with git only. Neither adds a second review reader.

## Cost

Counts per run. Each preview, draft step and ready `--confirm` runs the gh half, with or without a `Lanes:` line.

- gh half (`handed_check`): `reviewed_read` makes 2 list reads, and 3 gh calls per ready PR with a review log.
- Each compare is one `gh api` call. Against the base: one per open PR on the base that reads done, other than the integration PR. Against the integration head: one per handed PR, and one per Lanes-named open PR not in the batch. A handed PR named on `Lanes:` but not in the head is compared twice.
- git half (`handed_local`): runs only when the body has no `Lanes:` line that names a PR. No gh call.
  - 1 `git log` (`read_lanes`), then 1 `git merge-base --is-ancestor` per distinct merged-in parent in `base..head`.
  - Per lane tip (a merged-in parent not on the base): 1 `git rev-parse --is-shallow-repository`, since its ancestry read exited 1.
  - On a base that is not the default branch, and only when a lane tip is found: 1 `git fetch` of the default branch. Then 1 ancestry read per lane tip against it, plus the probe for each that exits 1.
  - A ready `--confirm` and a preview run `refuse_dropped_lane`'s `read_lanes` first. The git half repeats that read.
  - The fetch updates `refs/remotes/origin/<default>` and may add objects to the clone. Ancestry reads write nothing.
- Draft step on a non-default base with no ready checks opens one worktree. Per run: 2 `git fetch` (base, head), 1 `git rev-parse`, 1 `git worktree add`, then `git worktree unlock`, `git worktree remove --force` and `git worktree prune`. That is 7 git processes. It writes one checkout in a temp folder, with its admin files, and removes all of it.
- No long-lived process and no timer. No log file.

## Status

Built on all three paths in `merge/merge.py`. The roadmap step `runner-drops-handed-lane` is the build. Its refusals cite this decision.

Kind: process
Home: merge/merge.py
