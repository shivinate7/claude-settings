# The lane lint's chain refusal is blanket

**What.** The chain refusal in `lane_lint_push_hit` (`hooks/guard_merge.py`) refuses any push after a commit, merge, pull, rebase, cherry-pick, revert or am in the same call and checkout, whatever that commit holds. A clean commit costs one retry in every repo with a fast lint step; the retry rate, and how many such pushes would pass the lint, are unmeasured.

**Where.** `hooks/guard_merge.py`, `_lane_lint_push_hit` (lines 1047 to 1090), with `LANE_LINT_PUSH_CHAIN_REASON` (line 823) and `_LANE_CHAIN_VERBS` (line 828).

**Decision.** lane-lint-at-push (the lane lint's fast steps run before a push leaves) names the refusal as a lane pick, kept. The pick can be undone, so it is the lane's call (triage, 2026-11-08 10:52 CST, item 423 ruling). The other option is to allow with an unknown note. Also guard-that-cries-wolf-is-spent (a guard that cries wolf is spent): a refused clean push is a false alarm of that kind.

**Retire.** The owner's pick lands in decision lane-lint-at-push. A case in `hooks/test_guard_lane_lint_push.py` then pins the picked form: a chain push is refused with the chain remedy, or it is allowed with one unknown line.
