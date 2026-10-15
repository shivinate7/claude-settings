# Hold a change that still has a safety hole after round 3

## The question

After review round 3, what does a change do when it still has open findings? It merges, or it is held. A safety hole that main lacks decides which.

## Ruling

Owner rulings, 2026-10-14, CDT. The owner's words, recorded as a gist:

- 22:25: `i thought we established items that arent solved need to split from others that are to ensure ci is green and the merge isn't blocked, this is a good example where all my repos should have to hold this back from merging (nor work more on it till i come in to chime in and help unblock things`
- 22:27: `change merges after third review if there are known gaps in that it's gotten better but just not perfect, if after the third round u still have a safety violation, you've not gotten better`

The rule that follows:

- After round 3, a change merges on green when it is better than main.
- A safety hole is a guard, gate or check that lets through an act that main refuses or asks about.
- A change that still holds a safety hole main lacks is not better than main. It is held: removed from the batch, so the rest merges green.
- A held change opens no lane and gets no more work until the owner decides. A held change that is also red gets no red-CI split.
- Every other open finding becomes a named limit and a debt. It does not hold the change.
- The red-CI split in `review-cap-red-ci` (red CI is split, not a hole) still applies to changes that are not held.

## Why

The owner wants unsolved items split from solved ones. Then CI stays green and the merge is not blocked (22:25).

Two lanes passed review round 3 and still opened a safety hole that main did not have:

- Lane `silent-write-narrow`. A nested PowerShell path ending in `\` hid the next command from the guard.
- Lane `cap-ask-data`. `python /dev/stdin` let piped text write a protected file.

The rule before this ruling let each lane merge on green after round 3, as a named limit. Either merge would have left the guards weaker than main.

Protected outcome: no merge leaves a guard weaker than main. No open gap stays out of sight.

## Holes, named

- No check decides whether a change is better than main. The call is a reviewer's judgment. Debt: `safety-hole-test-is-judgment`.
- Round 3 of `agents/reviewer.md` does not tell the reviewer to list a safety hole apart from other findings. The orchestrator cannot read a hold from that report. Debt: `reviewer-round3-no-safety-tag`.

Debts: `safety-hole-test-is-judgment`, `reviewer-round3-no-safety-tag`.

Kind: process
Home: rule:roles-review-cap-three
