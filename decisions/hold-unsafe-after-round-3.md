# Hold a change that still has a safety hole after round 3

## The question

After review round 3, what does a change do when it still has open findings? It merges, or it is held. A safety hole that main lacks decides which.

## Ruling

Owner rulings, 2026-10-14, CDT. The owner's words, as the coordinator quoted them:

- 22:25: `i thought we established itemd that arent solved need to split from others that are to ensure ci is green and the merge isn’t blocked, this is a good example where all my repos should have to hold this back from merging (nor work more on it till i come in to chime in and help unblock things`
- 22:27: `change merges after third review if there are known gaps in that it’s gotten better but just not perfect, if after the third round u still have a safety violation, you’ve not gotten better`
- 22:29: `go on`, said to the fix lanes of the two held lanes, after the owner was told about them. It allowed work on those lanes. It did not allow a merge.

The rule that follows:

- After round 3, a change merges on green when it is better than main. Better than main means that the change holds no safety hole that main lacks.
- Read the hole narrowly: a hole main lacks, not any violation. Every guard has some known gaps on main, so "any violation" would hold every change. The owner is to confirm this reading on the morning list.
- A safety hole is a guard, gate or check that lets through an act that main refuses or asks about.
- A change that holds a safety hole main lacks is held. It is dropped from the batch, so the rest merges green. It is parked: it gets no fix lane and no more work until the owner decides.
- The owner's word can allow work on a held change, as at 22:29. A merge still needs no safety hole that main lacks.
- A held change that is also red gets no red-CI split.
- Every other open finding becomes a named limit and a debt. It does not hold the change.
- The red-CI split in `review-cap-red-ci` (red CI is split, not a hole) still applies to changes that are not held.

## Why

The owner wants unsolved items split from solved ones. Then CI stays green and the merge is not blocked (22:25).

Two lanes opened a hole that main did not have:

- Lane `silent-write-narrow` passed review round 3. The branch allows `pwsh -c "cd C:\x\; wsl --shutdown"`. Main denies it.
- Lane `cap-ask-data`. Its round-3 review found that `echo "import os; os.system('tee F </dev/null')" | python /dev/stdin` is allowed on the branch and denied on main, where F is a frozen path. The review probed the guard's verdict. It did not run the command live.

The rule before this ruling let a lane with an open hole merge on green after round 3, as a named limit. A merge of either lane would have left the guards weaker than main.

Protected outcome: no merge leaves a guard weaker than main. No open gap stays out of sight.

## Holes, named

- No check decides whether a change is better than main. The call is a reviewer's judgment. Debt: `safety-hole-test-is-judgment`.
- No check makes the orchestrator read the round-3 line `Safety hole vs main:` before a merge. Debt: `safety-line-unread-at-merge`.

Debts: `safety-hole-test-is-judgment`, `safety-line-unread-at-merge`.

Kind: process
Home: rule:roles-review-cap-three
