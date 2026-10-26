# One Opus agent hook reviews each question before the owner sees it

## The ruling

Owner rulings, 2026-10-22 10:18 CDT:

- One agent hook (`type: agent`) on PreToolUse `AskUserQuestion` in `settings.json` reviews each question. It replaces the Sonnet prompt hook and `hooks/question_outcome.py`, with their decisions (`question-outcome-check`, `question-judge-reads-rulings`).
- The model is a full Opus id, pinned in the hook. Opus runs by the owner's standing word of 2026-10-21, given at class level for this hook (row in `agent-model-cap`).
- The rubric is the hook prompt. There is no `agents/` file and no Read allow rule. A question with one option or none passes. Each other question needs:
  - a `Goal:` line first, then a `Problem:` line;
  - one to three `Based on:` lines, each with its source kind;
  - for each option, what the owner gains and loses;
  - a recommendation;
  - no unexplained ids, and nothing that points outside the box.
- Premises show in the box as `Based on:` lines. The reviewer checks that the lines exist and name a source kind, one of the kinds in `premise-format` (a premise names its source). The hook prompt lists those kinds itself, because a hook cannot point at `docs/decisions/`. Class `QuestionReviewer` in `lint/test_settings_matcher.py` keeps that list equal to the record. It does not check a premise against `docs/decisions/`, and no other check does.
- A failed or timed-out agent hook lets the question through.
- The reviewer judges the box alone. Whether the agent can read the chat, or `transcript_path`, is unmeasured.
- `lint/test_settings_matcher.py` (class `QuestionReviewer`) pins the hook: one agent hook, an Opus id, the agent-hook keys only, and each rubric item named in the prompt.

Dropped with the old judges, by the same ruling:

- the goal-match and option-serves-goal asks, which need the chat
- the settled-question check, which finds a question that a decision or a debt already settles. No check runs (`settled-question-check-gap`, no hook checks for a question a record settles).
- the "better option missing" ask
- the code check that denied a box whose Goal and Problem lines were out of order. The order is now model judgment, and a failed hook lets the question through.
- the deny-then-pass loop breaker
- the fixture suite for `question_outcome.py`

Risk kind: likely risk. A session puts a question with no goal, no problem or no stated gain and loss to the owner in normal work. Landed 2026-10-22.

Cost, counted from `settings.json`, per question with options. Before: 1 command hook, which starts bash, python, git and a `claude` child, and 1 prompt hook. After: 1 agent hook and 0 processes. Each question with options costs one Opus run, capped at 60 s (`timeout` in the hook).

Kind: process
Home: settings.json
