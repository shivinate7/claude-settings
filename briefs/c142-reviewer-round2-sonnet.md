# c142: a reviewer at round 2 or 3 runs Sonnet, not its definition's Haiku pin

Cloud build thread brief. Build advisor (10), Oct 27, against claude-settings main 6a3e842.
Send the green, reviewed head to the build advisor; never merge.

## Why
Measured Oct 27 (c54, PR #714, decision agent-model-cap): an agents/*.md model pin beats
CLAUDE_CODE_SUBAGENT_MODEL both ways. agents/reviewer.md pins Haiku, so a reviewer spawn with no
model field runs Haiku at rounds 2 and 3, against roles-third-try-steps-up ("Reviewers run Sonnet
from round 2 on"). The guard rule agent-model-floor refuses only a haiku model field, so nothing
catches a missing field.

## Task
Pick the smaller safe fix and say which you picked and why:
(a) hooks/guard.py asks for an explicit model on a reviewer spawn whose prompt says round 2 or 3; or
(b) agents/reviewer.md pins Sonnet, and round 1 names Haiku in its spawn if the table wants Haiku.
Check the model-per-role table (decision agent-model-cap) first; the fix must match it.
Red first: a round-2 reviewer spawn with no model field runs or passes as Haiku on main.

## Done when
The red case is a test, red on main 6a3e842 and green on your head; hooks tests green. This changes
a guard, so one fresh Sonnet reviewer hunts bypasses and false alarms (an ask on a round-1 spawn
is a false alarm). Report cap 15 lines. Port: no; agents and the guard install from claude-settings.
