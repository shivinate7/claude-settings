# Lane handoff: zizmor-shared-action

Written by the lane session, 2026-11-04 02:00 CST, for its coordinator. This file is a snapshot: read the live PRs first.

## State

- PR #1125 (the zizmor shared action): merged in batch 4.
- PR #1146 (multi-line with: reading), head 063bf45f, and PR #1148 (zizmor pin drift), head 0df82bc6. Both have main d7eb5c94 merged in. Lane lint PASS for each. Both are with the batch runner.
- Review: 2 rounds each. Round 2 (reviewer sonnet) gave merge on both.
- Source: docs/plans/child-guard-promotion.md, "Promotion lanes" item 3.

## Built

- actions/zizmor/: run.sh is the one home of the pin zizmor==1.30.1. checks.yml runs `$/actions/zizmor`. `bin/ci-job --lint` runs run.sh in place.
- #1146: `block_scalar` in lint/workflow_steps.py is the one reader of `|` and `>` values. It closes debt ci-job-multiline-with.
- #1148: bin/ste-changed checks zizmor pins for drift on the action's own files. The no-question grant covers ste-lint pins only. It closes debt zizmor-pin-drift-unchecked.

## Open

- Debt code-check-pin-drift: the code-check action runs in place, but its pin is not checked. It is added in #1148.
- Notes on these lanes are in docs/debts/notes.md: zizmor-env-unset-untested, zizmor-paths-doc-drift, zizmor-test-comment-files, run-header-comment-false-fail, multiline-value-edges.
- Child removals, each waiting for the owner's ask: banchi row 26, degen row 5, joyous row 1, mailaudit row 2, q_max row 10.
