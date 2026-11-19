# Handoff: lane guards-read-origin-main-config (2026-11-19)

- Slug: guards-read-origin-main-config. Session: session_013NEJL3e5VxTvDHtfBupKfs. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6.
- Step: guards-read-origin-main-config (guards read repo config from the origin/main blob, part b of the stale-checkout ledger row D14).
- Branch: `guards-read-origin-main-config`, pushed to origin, head `0153df4cb77d7f216ab54adb8bf0c222dad85bf9`.

## Open PR
- #3073, draft, head 0153df4cb, base 36807ad19 (main of 2026-11-12). Open, mergeable_state dirty. Trial merge with main bd0759f83 (2026-11-19) conflicts in 6 files: hooks/test_call_judge.py, lint/test_report_guard.py, lint/test_check_artifact_cites.py, tests/guard/s30130-rule9.py, and the product files lint/layout.py and lint/report_guard.py.
- Not marked ready. Handed in to batch runner 10 (session_013NEJL2f1YCYsvLdpFqtWP3) on 2026-11-13; runner 10 left it out of batches 123 and 124 for conflicts.

## Done
- Change: guards read `.claude/layout-extras.json` from the origin/HEAD, else origin/main blob (one `git cat-file --batch`). A fork (checkout file sets `record-branch`) keeps its own file, 0 starts. Checks that validate the checkout's own file (shared-resources, artifact-cites registry), writers, and the colour/icon reads stay file-only. One home: `lint/layout.py` `repo_keys`.
- Cost: page, artifact, devices, caution reads 1 git start (0 for a fork); `github_repo` 2; report relay 2; colour and icon 0.
- Review at head 0153df4cb: round 1 haiku FAIL, round 2 sonnet FAIL, round 3 (fresh full review) sonnet PASS, net value positive. Records posted on #3073. `merge --lane-lint 3073` PASS at 0153df4cb. `merge --reviewed` read it done.
- Decision text rewritten: docs/decisions/cross-repo-question-checked.md lines 17-21.

## Unfinished
- Merge main into the branch; the first attempt (test-author, name below) was lost in the 2026-11-19 container restart. Nothing of it was pushed.
- Round 3 named limits, not filed as debts or notes (editing the head would have forced a new review): (1) the `layout.py waiting-page` verb reads the blob, so after `set-waiting-page` a repo whose main lacks a page reads "unknown" until merge (candidate debt); (2) a fork with its own page and no `record-branch` reads main's page; (3) cost statements not re-stated at hooks/guard.py 4621, docs/decisions/session-tiers.md 48, hooks/session_start.sh 338, hooks/feedback_guard.py `filed_numbers`; (4) docstring lines at column 0, lint/layout.py 354-355.
- `hooks/test_guard.py` was never run whole by the lane; CI owns it.
- Part (a) of D14 (reversing step grants-read-from-main) waits on the owner. The retrospective brings it.

## Next step
Coordinator pick pending (sent 2026-11-19 00:30 CST): (a) fresh merge of main with a builder and a test-author, then fix verifier, record, lane lint, hand in; (b) close #3073 and re-cut on today's main (main's lint/layout.py already has `_default_branch_extras` at line 383); (c) park until the owner rules on part (a).

## Refused acts and rulings held
- Refused: `git worktree add` by hand (hand-made-worktree hook); checking out another branch in the pointer checkout (pointer-head hook); piping `verdict`; SendMessage to a session id; a second `--fix-check` in a record chain (decision pr-review-record: a second fix on a fixed head takes a fresh full review).
- Rulings held: Coordinator 2026-11-12 21:53 CST (pick a: blob wins, a fork keeps its own file; colour read stays file-only). Triage 21:52 CST said the colour test could move to one git start; the Coordinator's file-only ruling was followed. No owner ruling is held by this lane.

## Agents (names are session-local; their local branches are lost in the restart unless pushed)
- test-author ab84ed2266c0898e1: red cases and re-points, branches guards-read-origin-main-config, -build-round2, -fixture-fix (local only; contents are in pushed commits up to 0153df4cb).
- builder a9a25381104300d43: product changes, branch guards-read-origin-main-config-build (contents pushed up to 0153df4cb).
- record-writers a91d6cf89c3cef4e4, a9823d78bba562c04: decision text and cost sentence (pushed).
- reviewers a49cbf972746cdcff (round 1), a74408e2bc9cf195e (round 2), a1d07555a802f30a0 (round 3 at 5bdc9edce), a2d41be2908b8bc4a, ab7fa84f97dc2d318, a666aa095cbe701e8 (fix checks), afbfff26dd3d01b16 (fresh round 3 at 0153df4cb).
- test-author ae93e85d6d962060b: merge of main, lost in the restart, nothing pushed.
