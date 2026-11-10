# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL3ZtjRrvWWB5nAzQiv

## Reply at 2026-11-10T17:28:03Z UTC

IDLE (B). Lane past-ruling-on-send (session_013NEJL3ZtjRrvWWB5nAzQiv). Nothing runs; nothing is unpushed.
Goal: run the past-ruling judge on owner-question sends and page writes, plus its follow-ups.
State: every PR has a review record at its live head and is released to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za); each only waits for its merge.
- #1554 past-ruling-on-send at 8c6e52377, base main
- #1586 ruling-label-writer-match at d2620fa45, base #1554
- #1673 verdict-claim-needs-run at f9d09b9bf, base #1554
- #2195 past-ruling-owner-only at 4422fad7e, base #1554 (owner item 445 a, fix check PASS, net value zero)
- #2041 verdict-run-not-read at 24f81a69f, base #1673
Order: #1554 first, then #1586, #1673 and #2195 (each retargeted to main), then #2041.
Left:
- #1669 widening-question-not-asked at 17c6ceb5c, base main, has no record with runner 8 in my notes; check it.
- Triage item 764 closes when #2195 merges.
- Steps step-pick-claims-match-page (triage item 817) and notes-scope-own-lines (widen to: an agent commit touches only files its brief names) wait to be placed.
Files: hooks/call_judge.py (PAST_RULING_ITEM), hooks/question_form.py, lint/report_guard.py, docs/decisions/question-form.md, docs/debts/notes.md. Probe script and results are in this session's scratchpad (probe_prod.py, pp3_*.json).

