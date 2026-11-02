# Code, then one Opus call, reviews each question before the owner sees it

## The ruling

Owner rulings, 2026-10-22 10:18 CDT:

- One command hook, `hooks/call_judge.py`, on PreToolUse `AskUserQuestion` and `ArtifactData` in `settings.json` reviews each question, in the chat box and on the waiting page. It runs `question_form.chat_hit` first (decision `question-form`); a hit refuses with no model call. A box that passes goes to one model call. A waiting-page decision write that passes `question_form.item_hit` and carries `options` or `context` gets the same call, with the same eight items, one call for a whole batch (owner ruling, 2026-11-01 11:51 CST). A task item write (kind task, or any write that carries `steps`) that passes `item_hit` and carries `context`, `steps` or `options` gets that call too (coordinator follow-up to the same ruling). It replaces the Sonnet prompt hook and `hooks/question_outcome.py`, with their decisions (`question-outcome-check`, `question-judge-reads-rulings`).
- The model is a full Opus id, pinned in `hooks/call_judge.py`. Opus runs by the owner's standing grant of 2026-10-21, given at class level for this hook (row in `agent-model-cap`).
- The rubric is the prompt in `hooks/call_judge.py`. There is no `agents/` file and no Read allow rule. A question with one option or none passes. A page write is judged only for the fields it carries. The form lines, their order and the marks on each option are code's (`question-form`). The model keeps eight items, the eighth being the past-ruling check (decision `question-form`). The Goal is in the owner's terms; Problem, premises, gain and lose are plain; no id goes unexplained; nothing points outside the box; one option is recommended.
- One task rule joins the eight items, for a task's `steps` and `context` (the whole-unit rule). A step that tells the owner to replace text quotes the whole line or value it replaces, and shows the line after the change in full. The incident is waiting item 99 (2026-11-01). Its step said to change `GUARD_SHELL_SKIP=` to `GUARD_SHELL_SKIP=tree`, but the real line was `GUARD_SHELL_SKIP= scripts/guard-shell.py --hook`. Following the step dropped the script call. The rule is in the one prompt constant `PAGE_PROMPT`; the eight items stay one constant, `JUDGE_ITEMS`.
- Premises show in the box as `Based on:` lines. Code checks that the lines exist and name a source kind, one of `PREMISE_KINDS` (decision `premise-format`). Item 8 tests the question and its premises against the decision records, the debt records and the step rulings (decision `question-form`).
- A failed or timed-out model call on a question refuses once, with the `Unvetted:` remedy (decision `question-form`). A code refusal stands.
- The reviewer judges the box alone. Whether the agent can read the chat, or `transcript_path`, is unmeasured.
- `lint/test_settings_matcher.py` (class `QuestionReviewer`) pins the hook: one command hook that runs `call_judge.py`, an Opus id, the eight prompt items, and no premise kinds in the prompt.

Dropped with the old judges, by the same ruling:

- the goal-match and option-serves-goal asks, which need the chat
- the settled-question check. It came back as the past-ruling check, item 8 of the judge prompt (decision `question-form`, owner ruling 2026-11-01 18:48 CST: every question is vetted).
- the "better option missing" ask
- the refuse-then-pass loop breaker
- the fixture suite for `question_outcome.py`

Risk kind: likely risk. A session puts a question with no goal, no problem or no stated gain and loss to the owner in normal work. Landed 2026-10-22.

Cost, per question with options: one `call_judge.py` process. A box that fails the code check makes no model call. Any other box costs one Opus call, capped at 60 s. Per `ArtifactData` call: one process. It exits at once unless the action is `set`, `update`, `str_replace` or `batch`. It makes one Opus call only for an item write that passes the code check. The write carries `options` or `context` (a decision), or `context`, `steps` or `options` (a task). Or it is a `str_replace` on `context` or `options`. A closed item and a title-only update make no call. A lone task write costs one Opus call; a task in a batch joins the batch's one call. The bound stays one call per `ArtifactData` call.

Kind: process
Home: settings.json
