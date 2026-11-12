# Trial results: Ambition Lenses, blind grade

This page grades the Ambition Lenses trial by the method in plan `plugin-assess-three` (PR #1036,
section Trial). Arm A runs with no added text. Arm B runs with the plugin text added.

## Verdict

**No result.** The win rule needs 7 wins out of 8 decided cases. The grade has 6 complete cases.
Two cases have a winner, and arm B wins both. The other four are ties.

Both of arm A's losses come from one cause: a new prose sentence over the 30-word lint limit. Each
fix is one sentence split. The work itself is right in all 16 runs.

A null result does not confirm skip (plan, section Trial). It means that the trial found no large effect.

## Primary measure: accept as is

One blind Sonnet reviewer graded each diff. A "yes" means that the owner would merge the diff with no
change.

| Case | Arm A run | A accept | Arm B run | B accept | Winner | Gold standard |
| --- | --- | --- | --- | --- | --- | --- |
| tracking-turn-report-clash | sx | yes | lg | yes | tie | Both yes |
| option-letters-match | qm | yes | mf | yes | tie | Both yes |
| windows-live-lock-flake | ct | yes | ux | yes | dropped | Both yes |
| questions-reach-page | hv | no | tz | yes | B | Both yes |
| env-heredoc-false-alarm | jw | yes | rn | yes | tie | Both yes |
| other-checkout-scratch-false-alarm | kc | yes | vb | yes | tie | Both yes |
| red-main-stale-schedule | hz | no | qt | yes | B | Both yes |
| builder-test-edit-heredoc | py | yes | gd | not run | incomplete | Both yes |

- Cases graded: 6 complete pairs. Cases with a winner: 2, both arm B. The bar is 7 of 8.
- hv: the lint fails on `lane-pick-any-send.md`, a debt file, line 3, a 35-word sentence. Its report
  said the lint passed.
- hz: the lint fails on `docs/debts/notes.md` line 947, a 32-word sentence. Its report said the lint
  was green, from a check that does not run this lint.

### Dropped and incomplete cases

- **windows-live-lock-flake (ct and ux): dropped.** Both reports say the run read main's newer copy
  of the test before the fix. Main already held the merged fix. The method drops a case for a read
  past its base.
- **builder-test-edit-heredoc (py and gd): incomplete.** Run gd never finished. Run py is graded
  alone and is not in the win count.
- **Noise check (qm and ka): void.** Run ka read main's copy of `hooks/question_form.py`, which holds
  the fix.

## Secondary measures

Each row sums or totals the six counted cases per arm.

| # | Measure | Arm A | Arm B | Gold standard |
| --- | --- | --- | --- | --- |
| 2 | Checks pass | 4 of 6 | 6 of 6 | All pass |
| 3 | Work is right | 6 of 6 | 6 of 6 | All yes |
| 4 | Noise hunks | 2 | 0 | 0 |
| 5 | Skipped acts | 14 | 19 | 0 |
| 6 | Agent briefs with task, check and cap | 61 of 62 | 50 of 53 known, 8 unknown | Each does |
| 7 | Refusals per tool call | 39 / 216 = 0.18 | 58 / 250 = 0.23 | Lower |
| 8 | Report words | 2,406 | 2,657 | The brief's cap or fewer |
| 9 | Context tokens at end | 997,638 | 1,084,892 | Lower, at equal outcome |

- Measure 2 ran `ste-changed <base>` and each test file the diff touches, on Linux. The Windows-only
  cases skip on Linux, so a green row proves Linux only.
- Measure 9 is raw. The offset for arm B's text is unmeasured: no tokenizer count exists. The text
  is 3,439 words, per the coordinator.
- Measure 8 caps are in lines, not words, so the gold column has no word number.
- Measure 7 is rough. The guard rows may include the agents' rows. The tool-call counts are the lead
  session's own, and some are approximate.
- The lint of hv and hz is the same at their base 49a41651 and on main today. Their losses do not
  depend on the lint version. The original runs pass under their own linter and under main's.

## Per-run detail

| Run | Arm | Checks | Right | Noise | Skipped | Briefs full | Refusals / calls | Words | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gold | either | pass | yes | 0 | 0 | all | lower | cap or fewer | lower |
| sx | A | pass | yes | 0 | 4 | 5 of 6 | 4 / 20 | 245 | 129,831 |
| lg | B | pass | yes | 0 | 3 | 3 of 3 | 2 / 19 | 278 | 125,332 |
| qm | A | pass | yes | 0 | 4 | 10 of 10 | 4 / 22 | 341 | 137,958 |
| mf | B | pass | yes | 0 | 3 | 5 of 6 | 7 / 18 | 389 | 153,449 |
| ka | A | pass | yes | 0 | 1 | 7 of 7 | 4 / 20 | 356 | 130,685 |
| ct | A | pass | yes | 0 | 5 | 3 of 3 | 2 / 15 | 439 | 124,173 |
| ux | B | pass | yes | 0 | 4 | 6 of 6 | 3 / 19 | 322 | 137,975 |
| hv | A | lint red | yes | 0 | 0 | 11 of 11 | 8 / 59 | 480 | 205,418 |
| tz | B | pass | yes | 0 | 2 | 14 of 16 | 12 / 53 | 483 | 205,311 |
| jw | A | pass | yes | 0 | 4 | 11 of 11 | 13 / 59 | 389 | 203,562 |
| rn | B | pass | yes | 0 | 3 | 9 of 9, 8 unknown | 12 / 56 | 463 | 218,043 |
| kc | A | pass | yes | 1 | 0 | 11 of 11 | 5 / 28 | 351 | 154,831 |
| vb | B | pass | yes | 0 | 2 | 8 of 8 | 18 / 52 | 511 | 185,883 |
| hz | A | lint red | yes | 1 | 2 | 13 of 13 | 5 / 28 | 600 | 166,038 |
| qt | B | pass | yes | 0 | 6 | 11 of 11 | 7 / 52 | 533 | 196,874 |
| py | A | pass | yes | 0 | 6 | 19 of 20 | 15 / 43 | 459 | 195,785 |

## Calibration diffs

The real lane's diff for each case, graded the same way, blind.

| Case | PR | Accept | Gold standard |
| --- | --- | --- | --- |
| tracking-turn-report-clash | #966 | yes | yes |
| option-letters-match | #967 | yes | yes |
| windows-live-lock-flake | #941 | yes | yes |
| questions-reach-page | #1070 | unknown | yes |
| env-heredoc-false-alarm | #1076 | yes | yes |
| other-checkout-scratch-false-alarm | #1066 | yes | yes |
| red-main-stale-schedule | #1067 | yes | yes |
| builder-test-edit-heredoc | #1073 | yes | yes |

- #1070 is unknown: its branch carries other lanes' merges, so its own diff cannot be cut out.
- The shadow-case PRs were drafts, so each grade uses that PR's head at grading time.
- Graders of the five newest calibration diffs also guessed a setup: 3 said extra text, 2 said none. Neither setup made these diffs. The guesses are logged apart from the hit rate.

## Blinding check

After it scored, each reviewer guessed which setup made its diff. A hit rate well above one in two
means that the blinding leaked.

- Hits: 7 of 15 run diffs, 47%. One guess is missing: the guard `parallelism-no-mid-task-talk`
  refused the follow-up question.
- Reviewers guessed "extra text" 14 times out of 15, at 52 to 62% confidence. The guesses carry no
  signal, so the blinding held.
- One reviewer got the guess question after scoring. The other 14 saw it last in their how-to, so
  it reached them before scoring.

## Confounds

- **Checkout on main.** The startup hook moved each run's shared checkout to main, past the base.
  Five runs say so (lg, mf, ka, ct, ux). A read past base that a run did not report is unknown.
  The risk is in the original cases only. Main never held a shadow case's fix, since those PRs are
  still drafts. The counted original pairs, sx with lg and qm with mf, tie either way.
- **Global rules from main.** Both arms loaded today's rules, as the plan expects. Run lg's loaded
  style already held a version of its fix line.
- **Arm B text placement.** The shadow B runs had the text in the first message, after the
  step. The plan puts it in an added system prompt. The three original B runs (lg, mf, ux) have
  first messages that match their A twins, so their text was elsewhere. Unmeasured: whether it was
  the system prompt.
- **Lead calls only.** The past-base scan read lead-session tool calls. Calls made by the runs' agents
  are not in the session events, so they are unknown.
- **Reviewer role.** The reviewer role runs Haiku in round 1. The graders ran as Explore on Sonnet,
  under the `Audit:` marker, so they match the plan's Sonnet reviewer.

## Inputs

- Method: plan `plugin-assess-three`, section Trial, on branch `plugin-assess-three` (PR #1036).
- Runs: branches `archive/trial-<run>` on origin. Bases: 4b8037d4 for the original runs, except
  ce803316 for ct and ux. 49a41651 for the shadow pairs, except 9743a815 for jw and rn.
- Briefs: `docs/plans/trial-briefs/` holds each shadow brief, word for word.
