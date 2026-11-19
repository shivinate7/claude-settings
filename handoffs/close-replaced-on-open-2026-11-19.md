# Handoff: lane close-replaced-on-open (step close-replaced-at-open)

Written 2026-11-19 00:30 CST by the lane session (id session_013NEJL2Nvu4nQzrvujJc3vS, parent coordinator session_013NEJL1gw6EdrSyvHkTUEx6).

## State
- Slug: close-replaced-on-open. Step: close-replaced-at-open (owner ruling R66, item 691 a).
- PR 3347, MERGED 2026-11-15 07:12 UTC by shivinate7. Final head b3ed25b75371f3ae8a2b7380501787a4d99a765b (runner 10 merged main into it at the mark). Branch close-replaced-on-open is deleted on origin.
- Last head this lane handed in: c0e629ffe416627bb373bd80e9a88b379c072d0a. Review record comment 6889524536 (rounds 1 FAIL, 2 PASS; fix check PASS). Lane lint comment 6889714813 PASS.
- No open PR. No agent running. No server running.

## Done
- merge/merge.py: the merge tool closes each open same-repo PR that a PR body names as Replaces/Carries, or an integration PR's freeze lanes, with a pointer comment, at `--ready` and at integration lane-lint PASS. It reopens a Dropped lane the tool closed. Lane lint refuses a non-integration hand-in naming an open replaced PR.
- Prose: skills/ci-hygiene/SKILL.md step 8, docs/decisions/session-tiers.md line 78.
- Debt close-replaced-test-pins-nothing and notes were in the merged head (docs/debts/). They are not on main now: cause unread.

## Unfinished
- Notes PR owed to the coordinator (message 23:25 CST Nov 14): file the five notes and the ancestor-head limit again if still wanted: reopen-dropped-unreadable-comments-exit-0, replaced-draft-text-omits-close, replaced-scope-not-mechanized, replaced-list-misses-wrapped-forms, replaced-prefix-quadratic-on-stars, and debt close-replaced-test-pins-nothing (merge/test_lane_lint.py hand-closed case never seeds the comment list, so closed_by_tool is not proven). Check docs/debts first: the notes folder rule may have changed their home.
- Step close-replaced-at-open stays open: the step note's ancestor-head scope (a PR whose head is an ancestor of another open PR's head also closes) is not mechanized.
- Unmeasured: whether the cloud lets PATCH pulls/N state=closed through (hooks/route_rows.json has no row).

## Next step
Read docs/debts and the notes folder on main, then one notes PR and a hand-in to the coordinator. Then the ancestor-head lane if the step is wanted.

## Refused acts and refusals named
- merge --review-record refused --fix-check once (no earlier posted log). A fresh round 1 was taken instead.
- Silent-undo check refused a merge that rewrote main's sort_comment; fixed by putting main's lines back (sort_pointer), not by a Drops-lines trailer.
- Agent spawns with a model above the role's were refused by the model-cap hook; spawned without it.
- No override used. No check weakened.

## Owner rulings held
- R66, item 691 a (2026-11-13 20:03 CST, via consultant): close a replaced PR as soon as its replacement exists; mechanize it. Home: step close-replaced-at-open, session-tiers line 78.
- Coordinator 23:25 CST Nov 14: push nothing; notes PR after the merge.

## Agents (all finished; worktrees under .claude/worktrees/, branches not pushed unless named)
- test-author: aedb19a83766efdb0 (round-1 red tests), a56688ef3c8b6b237 (lost to a restart), a358dfeaddcee166f, a85e92b797c134a70, add3429501c5b00a2, ae57f92d297c89f67 and ad19503b204e3c829 (lint-fix edits). Pushed to close-replaced-on-open.
- builder: afda1f74590ff9467, a1689bb03cf51c7fe, af582b5c300261852 (opus, round 3), a692954dcb74c6112, a858c2a871d60f34b, a532cee0cb5eb3394, a8bc2256dc938ef58, aaa8dff1485983267, aa0b4b573cecc530d, ad98f07b133a8a4d5.
- reviewer: ad6aa38279d2d43a7, ac9a398d650483931, a3f96a58ba72438d4, a77a9e26ec512abf7, a577337ff59eb9d00, a1c326580c03eff94, a4ac24ebb44a099d6, ab8f46bec63a0da9e, aa6f2fcd806bbf8ee.
- record-writer: a7cfd2c0ab916e95d, a15959b832ae28fe1.
