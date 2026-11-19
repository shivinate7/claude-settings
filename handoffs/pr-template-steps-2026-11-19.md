# Handoff: lane pr-template-steps, 2026-11-19 00:30 CST

- Slug: pr-template-steps. Lane session session_013NEJKz3XYDCqNt8Jyi2hcj. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6. Batch runner 10: session_013NEJL2f1YCYsvLdpFqtWP3.
- Task: three roadmap steps found on PR 2613: pr-template-not-guard-path, find-copies-pr-template, pr-template-copies-equal.

## PRs (read from the GitHub REST API at 00:28 CST)

- PR 2706, branch pr-template-stays-guard, head 12e398038b2e: merged 2026-11-12 20:43 CST. Step pr-template-not-guard-path.
- PR 2707, branch find-copies-pr-template, head 0c9be1a51d8d: merged 2026-11-12 20:43 CST. Step find-copies-pr-template.
- PR 2708, branch pr-template-copies-equal, head now 042136d73608 (my last head was e7673f6f4): closed 2026-11-16 09:56 CST, not merged. Someone rebuilt it after the batch runner warned of a conflict with PR 2655, which rewrites the PR template line 18 that 2708 removes. Step pr-template-copies-equal looks unmerged. Unverified: whether it landed another way.

## Done

- Step 1 finding: `.github/pull_request_template.md` is correctly a guard path. All of `.github/` is in `stale_cites.RULE_DIRS`. The template seeds PR bodies the debt checks read, and `TemplateExcuses` in `lint/test_check_debt_retire.py` reads it in CI. The round 3 reviewer on 2613 read the list wrong. No code change. A record sentence in `docs/decisions/pr-review-record.md` and pin tests in `merge/test_merge.py` landed in PR 2706.
- Step 2: `lint/find_copies.py` skips a child's own PR template (`OWN_FILES`, `own_twins`, `near_score`). Rounds: haiku FAIL, sonnet FAIL, sonnet PASS; net value zero. Landed in PR 2707.
- Step 3: `lint/check_layout.py` keeps the two template copies byte-equal. Round 1 PASS (reviewer haiku). Not merged.

## Unfinished and next step

- Step 3: read `lint/check_layout.py` on main for the copies item. If it is absent, rebuild PR 2708 from branch pr-template-copies-equal (head 042136d73) on current main.
- Notes filed in `docs/debts/notes.md` with PR 2706: debt reader-claim-needs-grep; notes pr-template-copies-notes, find-copies-twin-gaps, find-copies-twin-name.

## Refused acts

- A haiku round 2 in a review record (merge tool, decision agent-model-cap). I reran round 2 on sonnet.
- A review record comment from a ref lint: a lint on a ref posts no comment, so I linted by PR number.

## Owner rulings held

- Grant (owner, 13:51 CST Nov 11): every ruled step starts after the guard test split lands. Used once for these three steps. Nothing else held.

## Agents (all finished)

- test-author and builder, branch pr-template-guard-path (first attempt, archived as archive/pr-template-guard-path); reviewer round 1 on it: FAIL (the template has a reader).
- test-authors and one builder, branch pr-template-stays-guard.
- test-authors, builders (one opus in round 3), reviewers rounds 1 to 3 plus a sonnet round 2 rerun: branch find-copies-pr-template.
- test-author, builder, reviewer round 1: branch pr-template-copies-equal.
