# Lane handoff: all-jobs-passed-wiring

Written by the lane session at wind-down, 2026-11-03, for its coordinator. This file is a snapshot: read the live PR first.

## State

- PR #1124 (draft), branch all-jobs-passed-wiring, head ff4926e8. Lane lint PASS. Sent to the batch runner.
- Review: 3 rounds. Round 3 PASS (reviewer sonnet), net safety value positive.
- Source: docs/plans/child-guard-promotion.md on PR #1119, "Promotion lanes" item 4.

## Built

- lint/all_jobs_passed_rules.py: the one home of the all-jobs-passed wiring rules. It holds the cs rules and child_problems.
- CLI: `python3 lint/all_jobs_passed_rules.py --workflow PATH` exits 0 when clean, 1 on problems, 2 when unreadable.
- lint/test_all_jobs_passed.py imports the rules and holds the child cases.
- The action step may not set its own `if` or `continue-on-error`. This holds in both rule sets.

## Rulings

- Process-only: a child job that runs only on push stays out of needs, because its own if decides whether it blocks a PR. Home: the module docstring.

## Open

- No child job runs this script yet, and the action does not call it. Proposed: a follow-up lane where a child job runs the script from a pinned cs checkout.
- Child removals wait on that lane: mailaudit row 5, q_max row 15 (PROMOTE ?), banchi row 46 (PROMOTE ?).
- Notes: five all-jobs-passed lines in docs/debts/notes.md.
