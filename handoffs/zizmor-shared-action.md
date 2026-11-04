# Lane handoff: zizmor-shared-action

Written by the lane session at wind-down, 2026-11-03, for its coordinator. This file is a snapshot: read the live PR first.

## State

- PR #1125 (draft), branch zizmor-shared-action, head 39a4e7e4. Sent to the batch runner.
- Lane lint: unknown, accepted with --lint-unknown-ok. Main's ci-job cannot run the new action; the lane's own `ci-job checks --lint` ran 63 PASS, 0 FAIL, zizmor PASS.
- Review: 2 rounds. Round 1 (reviewer haiku) found 2 defects, both fixed with red cases first. Round 2 (reviewer sonnet) verdict: merge.
- Source: docs/plans/child-guard-promotion.md on PR #1119, "Promotion lanes" item 3.

## Built

- actions/zizmor/: action.yml and run.sh. run.sh is the one home of the pin zizmor==1.30.1. Paths arrive through env ZIZMOR_PATHS (default .github/), split on spaces or newlines. Empty paths fail closed.
- checks.yml: the zizmor step runs `$/actions/zizmor` with paths `.github/ actions/`. Its suite actions/zizmor/test_action.sh is in the opt-in list.
- bin/ci-job --lint runs the action in place from run.sh. It needs no base.
- lint/workflow_steps.py: step_with, which shares one parser with step_env.

## Open

- Debt ci-job-multiline-with: a `paths: |` value in a child workflow reads as `|` under ci-job --lint. The child lanes will likely hit it.
- Debt zizmor-pin-drift-unchecked: ste-changed does not read zizmor pins. Owner question: extend the drift check, or put zizmor under the normal rule.
- Child removals, later lanes: banchi row 26, degen row 5, joyous row 1, mailaudit row 2, q_max row 10.
