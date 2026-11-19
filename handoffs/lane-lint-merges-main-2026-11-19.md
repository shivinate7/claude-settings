# Handoff: lane lint-merges-main, 2026-11-19

**Slug:** lane-lint-merges-main. **Repo:** shivinate7/claude-settings.
**Branch:** `lane-lint-merges-main`, head `68eabda54475d35fe7dd734e8e6176cc5ec96ede` (origin matches).
**Open PR:** #3552, draft, head 68eabda54. Not marked ready, not merged, no review record posted.

## What the PR does
`merge --lane-lint <pr>` merges main into a behind-main lane head as a real merge commit M (parents: old head, tip),
lints a lint commit L (parents: tip, M) with CI_JOB_HEAD_SHA = M, and on a full PASS pushes M (plain push) and posts the
lane-lint comment naming M. Push needs: PR number, open same-repo PR, base = default branch, not a batch integration PR,
not the batch runner's pre-join call, no Record-claim head, PR head an ancestor of the caller's checkout HEAD.
Why: owner ruling page item 925 d (decision merge-needs-current-base) names #3552 as needed.

## Done
- Code and tests on the branch; main merged in once (e8360bbb4). `merge/test_lane_lint.py` passes on 68eabda54.
- Reviews: round 1 haiku FAIL, round 2 sonnet FAIL, fix checks sonnet PASS at 37f4d0af, 6ad96e53, cf739ee02; a fresh sonnet
  round 1 at cf739ee02 FAIL (findings fixed); fix check sonnet PASS at 68eabda54. No review record is posted: the tool
  refused a haiku round 1 (agent-model-cap row) and a fix check with no earlier record.
- Runner 10 lane lint PASS at cf739ee02 (19:54 CST Nov 17); it does not carry to 68eabda54.
- `merge/test_merge.py` RedMainBrake errors (176) also fail on main (scratch copy of main).

## Unfinished
1. Owner pick on page item 951 (lane-lint-push-needs-flag): option a (amend the "Merge Tool Read Checks" allow entry in
   settings.json and docs/decisions/auto-mode-owner-acts.md so `--lane-lint` may push the main-in merge) was relayed by
   triage 11 as typed 11:57 CST Nov 18. The classifier refused the builder spawn that would edit the entry; I asked the owner
   to confirm in this lane's chat. Not confirmed. Option b was a `--merge-main` flag (my earlier recommendation).
2. Red pins for the amended entry sit on origin `lane-lint-merges-main-tests7` (3b1743f39, 9 red cases), not merged
   into the PR branch. The candidate entry text is in the scratchpad file make_candidate.py (session scratchpad, may be gone).
3. Lease finding (plain push has no lease; a deleted PR branch is recreated at M): not filed as a note.
4. Six of eight skip-reason texts are not pinned by tests (reviewer note).

## Next step
On the owner's word for item 951: builder amends settings.json entry and the decision to tests7's pins, fix check, post the
review record through the tool (fresh sonnet round at the live head, Guard or check yes), ask runner 10
(session_013NEJL2f1YCYsvLdpFqtWP3) to lint the final head, mark ready, merge. If b: add the flag (test-author, builder, fix check).

## Refused acts
- Classifier ("Undermining Oversight") refused `Agent` for the builder that edits the settings.json allow entry.
- Record tool refused round 1 haiku (below its row's sonnet) and `--fix-check` with no earlier record.
- Hooks refused hand-made git worktrees for red-run checkouts (test-authors ran red in their own worktree).

## Owner rulings held
- Page item 925 d, 2026-11-17 14:20 CST (merge-needs-current-base): "Lanes bring main in only on conflict; the merge tool does one
  main-in at merge time ... (needs #3481 and #3552 on main)."
- Own-lane-lint-allow-b, 2026-11-15 11:30 CST: covers the allow entry and that act only (a push is a variant).
- Item 951 pick a: relayed only (triage 11, 12:00 CST Nov 18); not read on the page by this lane.

## Agents (all finished; worktrees gone unless noted)
- test-author haiku: branches lane-lint-merges-main-tests, -tests2, -tests3, -tests4, -tests5, -tests6, -tests7 (origin).
- builder sonnet: lane-lint-merges-main-build, -build2, -build3, -build4 (origin).
- reviewers: round 1 haiku, round 2 sonnet, fix checks sonnet x4, fresh round 1 sonnet (reports in the session only).

## Sessions
Coordinator session_013NEJL1gw6EdrSyvHkTUEx6; runner 10 session_013NEJL2f1YCYsvLdpFqtWP3; triage 11 / page writer session_013NEJKzyLYRTQKeLpis8JKJ.
