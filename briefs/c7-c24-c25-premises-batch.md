Premises batch, claude-settings. Roadmap: c7 (fix the reply-style conflict: one question reviewer), c24 (planners check their brief's premises), c25 (handoffs list premises with sources, evidence lives in its record). Attach plans/premise-handoffs-plan.md with this brief; it is the design, with file and line references checked at 73ed71a7. Re-check each reference against current main before editing, since other batches have merged since.

Order: after the guard-rule batch (c10, let the guard grow then cull what never fired; l1, rules that never fired show up) lands. Fixes and tests only; no measuring step.

Owner's rulings, Oct 21 (all four open questions in the plan, answered A):
1. Premises show inside the question box: one to three short "Based on:" lines in plain words, each with its source kind.
2. Drop the code check for the Goal and Problem lines; the question reviewer judges form too.
3. The question reviewer runs on Opus by a standing class-level word, recorded in decision subagent-model-cap (like the audit Explore word of 2026-10-21).
4. Raw evidence lives inside the decision or debt that uses it, in an Evidence section of about 10 lines, deleted with that record. Add that one clause to decision cull-rules in place.

Lanes, as in the plan's section 5:
1. Probe agent hooks first, alone. Report which of the plan's checks hold. If agent hooks do not work, stop and report before any other lane; the fallback (the session spawns the reviewer itself) costs about five processes per question on Windows and needs the owner's word.
2 and 3. The premise section in the handoff and the premise format's one home (same files: one builder, or 3 after 2).
4. The question reviewer: agents/question-reviewer.md with model opus pinned, one agent hook on AskUserQuestion.
5. Delete the old judges (the AskUserQuestion prompt hook and hooks/question_outcome.py, with their tests, decisions and references). Needs 4 merged.
6. The planner duty in agents/plan.md: premises first, checked against decisions/ and recent rulings. Can run beside 2 to 4.
7. The evidence clause in cull-rules (wording only).
8. Handoff cadence (owner's ruling, Oct 21). (a) The Stop nudges to rewrite the handoff move from fixed token counts (200k, 350k, 450k, precompact_handoff.py) to fractions of autoCompactWindow, about 40, 70 and 90 percent, so they still fire if the window is lowered. Test: with the window set to 250k, all three nudges fire; red on main. (b) hooks/precompact_handoff_prompt.md gains a rule: also update the handoff with a small edit when something happens (an owner ruling, a finished step, a test result that changes what fails); the token nudges stay as the backstop. Shares files with lane 2: same builder, or after it. (c) The PreCompact digest (precompact_handoff.py, state/handoff/<sid>.digest.md) keeps every owner message word for word, not only the last 60,000 characters, with long pastes cut to their first lines and marked as cut. Digest file only; nothing new loads into context. Test: an owner message from early in a long transcript is in the digest verbatim, and a long paste is cut; red on main.

Each lane: a test red on main and green on the fix, as the plan lists. Record each ruling in place under decisions/.

Report: per lane, what changed and the test that proves it; lane 1's findings in full; the net hook processes per question on Windows, before and after, counted from settings.json; and the four size numbers on main.
