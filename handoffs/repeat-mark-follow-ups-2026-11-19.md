# Handoff: lane repeat-mark-follow-ups (2026-11-19)

- Slug: repeat-mark-follow-ups. Parent: coordinator session_013NEJL1gw6EdrSyvHkTUEx6.
- Task (relay, owner's word via consultant 23:07 and 23:09 CST Nov 14): merge main into draft PR branches 2781 then 2957, push once each, post record and lane lint, hand in. Drafts stay draft. Never ready, merge, force push or close.

## Open PRs
| PR | Branch | Head | Parents | State |
|----|--------|------|---------|-------|
| 2781 | repeat-judge-never-blocks | 1a58c58c77f4b161d21542975f3ee86b3a513175 | 2f2240621, dc35317d3 | draft, not handed in |
| 2957 | repeat-mark-skips-followups | d88055715d6062ea1c3e88a21a2e654e52695e5a | fd96ffc4e, dc35317d3 | draft, not handed in |

## Done
- Both merges of main pushed once, no conflict markers (2781: notes.md by union driver; 2957: clean).
- Tests at both heads PASS: hooks/test_feedback_inbox.py, test_waiting_export, test_settings_matcher, check_red_run, ste_lint on touched records.
- 2781 review record posted: PR comment 6889715265 (fix check a6cd56c13 PASS, sonnet).
- 2957: no new record (clean merge keeps the old record at fd96ffc4e, per decision pr-review-record).

## Unfinished
- Lane lint FAILs on both heads: Checks step scope suite, lint/test_checks_step_scope.py test_each_scoped_entry_names_no_tracked_md_file_it_does_not_list, entry hooks/test_feedback_inbox.py names docs/debts/notes.md. No lane-lint comment on either PR.
- Coordinator ruling 23:48 CST Nov 14: leave 2781 to combine PR 3435 (do not push the test edit, do not hand in 2781); hold 2957 until 3435 merges, then merge main once, push, record, lint, hand in.
- Read at 00:25 CST Nov 19: PR 3435 is merged (merged_at 2026-11-15T06:59:50Z, head 0eda7cfb0, REST). 2781's state and 2957's rebase were not re-read after that.

## Next step
Read 2781 and 2957 state by REST. If 2781's change is on main, say so and stop on it. For 2957: fetch main, merge once, check the record and lint, push once, hand in.

## Refused acts
None refused. Acts left undone by order: test edit and second push on 2781; ready, merge, force push, close.

## Rulings held
- Grant: relay of owner's word, 23:07 and 23:09 CST Nov 14; record roadmap/rulings/own-draft-rebase-lanes.json on origin/roadmap (named by the coordinator, not read by this lane).
- Coordinator 23:48 CST Nov 14: leave 2781 to 3435; hold 2957.

## Agents
- Fix verifier (reviewer, sonnet), finished: PR 2781 merge check, PASS, no branch (read-only).
- No other agents. Local branches: repeat-judge-never-blocks, repeat-mark-skips-followups (both match origin).
