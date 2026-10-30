# Code, then one Opus call, reviews each question before the owner sees it

## The ruling

Owner rulings, 2026-10-22 10:18 CDT:

- One command hook, `hooks/call_judge.py`, on PreToolUse `AskUserQuestion` in `settings.json` reviews each question. It runs `question_form.chat_hit` first (decision `question-form`); a hit refuses with no model call. A box that passes goes to one model call. It replaces the Sonnet prompt hook and `hooks/question_outcome.py`, with their decisions (`question-outcome-check`, `question-judge-reads-rulings`).
- The model is a full Opus id, pinned in `hooks/call_judge.py`. Opus runs by the owner's standing grant of 2026-10-21, given at class level for this hook (row in `agent-model-cap`).
- The rubric is the prompt in `hooks/call_judge.py`. There is no `agents/` file and no Read allow rule. A question with one option or none passes. The form lines and the marks on each option are code's (`question-form`). The model keeps four items: each option's gain and lose are plain effects on the owner, no unexplained ids, nothing points outside the box, one option is recommended.
- Premises show in the box as `Based on:` lines. Code checks that the lines exist and name a source kind, one of `PREMISE_KINDS` (decision `premise-format`). No check tests a premise against `docs/decisions/`.
- A failed or timed-out model call lets the question through. A code refusal stands.
- The reviewer judges the box alone. Whether the agent can read the chat, or `transcript_path`, is unmeasured.
- `lint/test_settings_matcher.py` (class `QuestionReviewer`) pins the hook: one command hook that runs `call_judge.py`, an Opus id, the four prompt items, and no premise kinds in the prompt.

Dropped with the old judges, by the same ruling:

- the goal-match and option-serves-goal asks, which need the chat
- the settled-question check, which finds a question that a decision or a debt already settles. No check runs (`settled-question-unchecked`, no hook checks for a question a record settles).
- the "better option missing" ask
- the code check that refused a box whose Goal and Problem lines were out of order. Order is unchecked.
- the refuse-then-pass loop breaker
- the fixture suite for `question_outcome.py`

Risk kind: likely risk. A session puts a question with no goal, no problem or no stated gain and loss to the owner in normal work. Landed 2026-10-22.

Cost, per question with options: one `call_judge.py` process. A box that fails the code check makes no model call. Any other box costs one Opus call, capped at 60 s.

Kind: process
Home: settings.json
