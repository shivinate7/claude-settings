# Plan: PR review depth by change kind

Status: draft for the owner's pick. Nothing in this plan is a ruling.
Drafted: 2026-11-17 21:38 CST, lane `lane/pr-template-risk-tiers`, from main commit 69ab998832.
Step: `pr-template-risk-tiers` (PR template lines, and review depth set by the change).

## Template lines

- Testing: already in both template copies as `## Test plan`. No line added.
- Risk: added as `## Risk` in both copies. It asks for the change kind, the review rounds owed, and what breaks if the change is wrong.
- How to revert: added as `## How to revert` in both copies.
- The copies differed on main by one sentence. The `.github` copy held a fragment that cited two decisions. Both copies now hold two plain sentences that cite the same two decisions.
- The copies check (`check_layout.py`, on branch `pr-template-copies-equal`) fails on main's copies and passes on this patch.

## Tier table

Read from main at 69ab998832. A cell `unset` means no decision says it. The owner picks the depth. This table picks nothing.

Ids used here:

- `roles-review-cap-three`: the rule that a change gets at most three review rounds. Its home is `hold-unsafe-after-round-3`.
- `hold-unsafe-after-round-3`: the round rules, the net-value test, and the list of guard or check paths.
- `pr-review-record`: the review record on each PR, and its done rules.
- `agent-model-cap`: the model and effort of each role and each review round.
- `docs-only-prs-skip-review`: a docs-only PR gets a short round, not a full review.
- `session-tiers`: the session roles, and who merges.

`Kind` and `Guard or check` are fields of the review record (`pr-review-record`).

| Change kind | Kind, Guard or check | Rounds owed after a pass; last round | Round 1 model | Fix verifier | Who merges |
|---|---|---|---|---|---|
| docs only | docs-only, no | 0; last round 3 | None owed. A record that files an owner ruling gets one round, on haiku (`docs-only-prs-skip-review`). | Open, when no round is owed (`pr-review-record`) | Batch runner |
| tests only | normal, no | 1; last round 3 | haiku | sonnet, xhigh | Batch runner |
| product code | normal, no | 1; last round 3 | haiku | sonnet, xhigh | Batch runner |
| guard or check | normal, yes | 1; last round 3 | sonnet, xhigh | sonnet, xhigh | Batch runner |
| merge tool | normal, yes for an edit to a merge/ check; no otherwise | 1; last round 3 | unset (see gaps) | sonnet, xhigh | Batch runner |
| rule text | normal, unset (see gaps) | 1; last round 3 | unset (see gaps) | sonnet, xhigh | Batch runner |

Notes on the table:

- Round 1 model is the `1 guard` row (sonnet) when the brief's first line says `Guard or check: yes`, and the `1 other` row (haiku) otherwise (`agent-model-cap`, the round rows).
- Guard or check is yes when the PR edits a listed guard or check path. Test files alone never count (`hold-unsafe-after-round-3`).
- Net value: a guard or check change owes net value after a failed last round. Negative net value holds any change, whatever its rounds say (`hold-unsafe-after-round-3`).
- Fix verifier: sonnet, xhigh on every PR (`agent-model-cap`, `pr-review-record`). A PASS ends review after any round. A FAIL stays open.
- Round 2 is sonnet, high. Round 3 is sonnet, xhigh. The builder's third try is opus (`agent-model-cap`, the round rows).
- Delete-only is a third Kind. With no guard or check, it owes one round, and its last round is 1. With a guard or check, it owes one round, its last round is 3, and it owes net value (`agent-model-cap`, the review rows).

Who merges (`session-tiers`):

- The batch runner runs every merge. Two cases differ.
- A lane merges its own claude-settings PR (ruling `own-lanes-merge-claude-settings-prs`, owner, 11:12 CST Nov 15). The cloud merge tool still refuses that confirm.
- A coordinator, triage or consultant merges its own PR in the cloud, under the standing merge role (ruling `own-tiny-fixes-b`, owner, 00:50 CST Nov 15). A docs-only PR needs no review record. Any other PR needs one passing sonnet reviewer record. That reading is the record-writer's, not a ruling.

## Gaps and conflicts

1. Unset: rule text. `hold-unsafe-after-round-3` lists guard and check paths. Rule text is not on that list. No decision says whether it counts.
2. Unset: merge tool. The list names merge/ checks, not all of merge/. No decision says which merge/ files count.
3. Conflict: who merges. `session-tiers` says "The coordinator and triage never merge." The standing merge role lets the coordinator and triage merge their own PRs. Both stand as written.
4. Conflict: one-lane runs. Rule `roles-solo-reviews-logic-diffs-only` says that in a one-lane run, other edits merge on passing checks alone. The table owes one round for tests only.

## Question for the owner

Pick a reading for each gap. Options and a recommendation:

- Rule text. (a) Not a check: haiku, one round. (b) A check: sonnet, one round. Recommend (a). A rule-text PR that edits a guard already counts as a check through the list.
- merge tool. (a) Only merge/ check files count: sonnet on those, haiku otherwise. (b) All of merge/ counts: sonnet on any merge/ edit. Recommend (a), which matches the list as written.
- Who merges. (a) Coordinator and triage merge their own PRs in the cloud, as the Nov 15 ruling says. (b) They never merge, as the Nov 2 bullet in `session-tiers` says. Recommend (a), the later ruling.
- One-lane tests only. (a) One round, as the table says. (b) Checks alone, as the solo rule says. Recommend (a).

## Next after the pick

1. Record the pick in a decision record. Its home is `hold-unsafe-after-round-3`.
2. The test-author writes the template-check cases first, and shows them red on main's copies.
3. The builder changes the check until those cases go green.
4. `docs/records.md` is a generated index and does not list this plan yet. It is not regenerated here.
