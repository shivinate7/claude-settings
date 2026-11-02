# Handoff: lane questions-reach-page (trial run, cs-step trial-tz)

Goal: make an Input Needed question reach the waiting page by mechanism, not by promise (owner incident,
2026-11-01 23:26 CST). Keep chat first (decision questions-go-to-owner, "Chat first, then the page").

Trial rules: base 49a41651; push only to `archive/trial-tz`; no PR; message no session.

## State

- Branch `archive/trial-tz`, head before this file: cbecc39a5 ("Record the pick send-text debt and three
  pick-check notes"). 11 lane commits on 49a41651. No PR (trial).
- Review: round 1 (reviewer haiku) FAIL with 6 fixes, all fixed; round 2 (reviewer sonnet) PASS. Round 3 not
  needed. Net-value test not run (it runs after round 3 only).
- Checks: lint/test_report_guard.py, hooks/test_local_time.py, hooks/test_feedback_inbox.py pass;
  hooks/test_guard.py exit 0, no FAIL; check_silent_undo --strict pass. `ci-job checks --lint` fails on one
  check only: the docs/records.md row for the new debt, which only the merge rebuilds (guard records-page).

## Done

- lint/report_guard.py: an owner-facing pick still unsent 5 minutes on blocks at Stop. A lane's pick blocks
  unless the same turn sends it to the parent or the writer. A send counts only when it carries the pick (item
  id, or the first 60 characters of its first line). State: `<handoffs>/<session_id>.open-picks.json` and
  `.open-picks.json.sent` (24 h memory of sent picks).
- hooks/guard_merge.py `own_tier` (tags and parent, one home); hooks/local_time.py `open_picks_path`;
  hooks/feedback_guard.py `names_token`, `writes_where`; hooks/shared_names.py `NOTICE_TAGS`.
- Records: decisions questions-go-to-owner and decisions-reach-a-clickable-pick, skill waiting-page, debt
  pick-send-text-match, 3 lines in docs/debts/notes.md.

## Next

1. Rebase on current main, open the draft PR, hand branch, head and PR to the batch runner.
2. Let the merge rebuild docs/records.md (clears the one lint red).

## Open questions (owner)

- An owner chat message clears an open item with no send to the writer. Must the check also require the send?
  Departs from: questions-go-to-owner "Chat first, then the page" (a chat answer still goes to the writer).
- Root CLAUDE.md rule questions-go-to-owner still says a lane's question "goes in its report". May it say the
  lane also sends it to its parent by send_message in the same turn?

## Left by agents

- Stray branch `questions-reach-page-tests-tests2` on origin (test-author pushed it against the trial rule).
  Not deleted: a delete is a push outside `archive/trial-tz`.
- Local branches only (all contained in the archive head): qrp-build, qrp-build2, qrp-build3, qrp-tests2,
  qrp-tests3, qrp-final, qrp-final2, qrp-records, questions-reach-page. Agent worktrees under
  .claude/worktrees/ remain for the janitor sweep.
