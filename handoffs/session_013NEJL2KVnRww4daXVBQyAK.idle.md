# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2KVnRww4daXVBQyAK

## Reply at 2026-11-10T17:26:57Z UTC

IDLE (B)
Goal: step pick-ack-past-ruling. New guard rule `pick-names-rulings`: a send_message that takes a pick departing from main (a `Departs from:` line), or the first reply to one, must name a real decision in a `Checked:` line, or the guard asks.
State: PR #2084, draft, branch pick-ack-past-ruling, head 7c8973098. Everything is pushed and no agents are running. It was handed to batch runner 8 on Nov 8 and is still unmerged.
Review: rounds 1-3. Round 3's net value was zero, so it was not held. A fix check then passed. `merge --lane-lint 2084` passed on 7c8973098.
Files:
- hooks/guard_merge.py (pick_ack_hit, _inbound_pick, _own_id)
- hooks/guard.py (the call, rule line)
- hooks/own_session.py (own_record_id)
- lint/_transcript.py (peer_sender frames=True, opt-in)
- hooks/question_form.py (pick_candidates, _top_overlap, without_fences)
- hooks/mutate_guard.py (18 pick mutants)
- tests: hooks/test_pick_ack.py, lint/test_report_guard_route.py
- .github/workflows/checks.yml
- records: docs/decisions/pick-names-rulings.md, skills/project-ops/templates/brief.md, docs/debts/notes.md (5 pick-ack notes)
What is left:
- Base e2703c611 is far behind main, and GitHub showed a conflict on Nov 8. The batch needs a conflict fix, then CI and the merge.
- Open notes (Fix: none, Until: 2026-11-21): `~~~` fences; `- 1.` lines; transcript parse cost; `Departs from: — none` asks; any real id passes unread; a test-author's worktree went missing mid-lane.

