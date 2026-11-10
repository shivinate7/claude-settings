# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL38w4WDs3n4aTNNHkB

## Reply at 2026-11-10T17:27:35Z UTC

IDLE (B). Handoff, lane option-tradeoff-pushback:
- Goal: the question judge sends back a question whose every option loses something large, and asks for one more option that keeps the gains (owner ask ask-mw80xweioa, 2026-11-08 10:05 CST).
- PR #2173 (draft), branch lane/option-tradeoff-pushback, head 9309aa81d, base main 422cbbdfe. Everything is pushed. Handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-08 at 12:29 CST.
- State: review rounds 1-3 are done. Round 3 (reviewer sonnet) passed, with net safety value positive. Lane lint passed. hooks/test_call_judge.py passes all checks.
- Files: hooks/call_judge.py (TRADEOFF_RULE and the is_pick_of_one skip), hooks/test_call_judge.py, docs/decisions/question-form.md.
- Left: rebase onto current main (it is about 2 days behind), CI, then the merge by the batch runner on the owner's word or a grant.
- Filed (Fix: none, Until 2026-11-21): an options-only update of a task with no kind still gets the rule (the same gap is in question_form); one test pins the re-ask wording; two test docstrings say "gate".
- Not built: a wider rule that also counts "goes against a ruling" and "leaves a gap open" as large. It caught item 416 but refused 6.1% of clean past items, so per triage's 11:37 CST ruling it was not built.
- Unmeasured: the chat-box path, and how often the rule catches real forced-loss questions.
- Scratch measure scripts are in this session's scratchpad (m/measure_hook.py, m/live.py); they are not in git.

