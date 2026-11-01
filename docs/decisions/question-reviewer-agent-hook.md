# Code, then one Opus call, reviews each question before the owner sees it

## The ruling

Owner rulings, 2026-10-22 10:18 CDT:

- One command hook, `hooks/call_judge.py`, on PreToolUse `AskUserQuestion` and `ArtifactData` in `settings.json` reviews each question, in the chat box and on the waiting page. It runs `question_form.chat_hit` first (decision `question-form`); a hit refuses with no model call. A box that passes goes to one model call. A waiting-page decision write that passes `question_form.item_hit` and carries `options` or `context` gets the same call, with the same seven items, one call for a whole batch (owner ruling, 2026-11-01 11:51 CST). It replaces the Sonnet prompt hook and `hooks/question_outcome.py`, with their decisions (`question-outcome-check`, `question-judge-reads-rulings`).
- The model is a full Opus id, pinned in `hooks/call_judge.py`. Opus runs by the owner's standing grant of 2026-10-21, given at class level for this hook (row in `agent-model-cap`).
- The rubric is the prompt in `hooks/call_judge.py`. There is no `agents/` file and no Read allow rule. A question with one option or none passes. A page write is judged only for the fields it carries. The form lines, their order and the marks on each option are code's (`question-form`). The model keeps seven items. The Goal is in the owner's terms; Problem, premises, gain and lose are plain; no id goes unexplained; nothing points outside the box; one option is recommended.
- Premises show in the box as `Based on:` lines. Code checks that the lines exist and name a source kind, one of `PREMISE_KINDS` (decision `premise-format`). No check tests a premise against `docs/decisions/`.
- A failed or timed-out model call lets the question through. A code refusal stands.
- The reviewer judges the box alone. Whether the agent can read the chat, or `transcript_path`, is unmeasured.
- `lint/test_settings_matcher.py` (class `QuestionReviewer`) pins the hook: one command hook that runs `call_judge.py`, an Opus id, the seven prompt items, and no premise kinds in the prompt.

Dropped with the old judges, by the same ruling:

- the goal-match and option-serves-goal asks, which need the chat
- the settled-question check, which finds a question that a decision or a debt already settles. No check runs (`settled-question-unchecked`, no hook checks for a question a record settles).
- the "better option missing" ask
- the refuse-then-pass loop breaker
- the fixture suite for `question_outcome.py`

Risk kind: likely risk. A session puts a question with no goal, no problem or no stated gain and loss to the owner in normal work. Landed 2026-10-22.

Cost, per question with options: one `call_judge.py` process. A box that fails the code check makes no model call. Any other box costs one Opus call, capped at 60 s. Per `ArtifactData` call: one process. It exits at once unless the action is `set`, `update` or `batch`. It makes one Opus call only for an item write that carries `options` or `context` and passes the code check.

Kind: process
Home: settings.json
