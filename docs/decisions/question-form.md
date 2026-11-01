# One question form, one guard, for the chat box and the waiting page

## The ruling

Owner steer, 2026-10-30 12:50 CDT: a question to the owner has one form and one guard, for the chat question box (`AskUserQuestion`) and for a waiting-page item write. Rewrite the guards as one; never add chat guards beside the page guards.

- The form. A decision on the page (in `context`), or a chat question with two or more options (in the question text), has these lines in this order:
  - `Goal: <the goal, in the owner's terms>`
  - `Problem (<stake>): <the problem in one plain sentence, and why it needs his word>`. The stake is one of `goal`, `money`, `risk`, `rule`, `cannot undo` (constant `OWNER_STAKES`). A stood pick (`stands: true`) may write `Problem: <text>`.
  - one to three `Based on (<kind>): <one premise>` lines. The kind is one of `PREMISE_KINDS` in `hooks/precompact_handoff.py` (decision `premise-format`).
- Each option states its gain and its loss: a page option has non-empty `gain` and `lose` fields; a chat option's description holds `Gain: <text>` and `Lose: <text>`.
- A widening option carries the mark and is never the pick: `widens: true` on the page, never in `pick`; in chat, the words "Goes against your uniform ruling (t18)" in its label or description, and no `(Recommended)` in its label (decision `uniform-over-variants`).
- A press in a web app carries a link: `links` on the page, an `https://` url in the option's description in chat (decision `act-in-place`).
- Code checks the lines, their order and the marks. `hooks/question_form.py` is the one home: `item_hit` for a page write, `chat_hit` for a chat box, and `page_item_hit`, the one filter of which `ArtifactData` writes are item writes of this repo's waiting page. `hooks/guard.py` calls `item_hit` through that filter and refuses a hit. `hooks/call_judge.py` calls `chat_hit` before any model call and refuses with the rule it names. Both places then get the same model review (owner ruling, 2026-11-01 11:51 CST). A chat box that passes goes to the question judge model. So does a page write of a decision that passes `item_hit`, is not closed, and carries `options` or `context`. So does a page write of a task (kind task, or any write that carries `steps`, since steps are task-only) that passes `item_hit`, is not closed, and carries `context`, `steps` or `options`. So does a `str_replace` on `context` or `options` that passes `item_hit`. The `ArtifactData` `str_replace` `field` is one top-level string key, so it never reaches `steps`, a list. A task adds one rule to the seven items, the whole-unit rule: a step that tells the owner to replace text quotes the whole unit it replaces (the whole line or value) and shows the line after the change in full. Its incident is waiting item 99 (2026-11-01): the step said to change `GUARD_SHELL_SKIP=` to `GUARD_SHELL_SKIP=tree` while the real line was `GUARD_SHELL_SKIP= scripts/guard-shell.py --hook`, and following it dropped the script call. A `str_replace` is judged on its `new_str` alone, never `old_str`, as a fragment: the prompt tells the model to judge only plain words, unexplained ids and pointers outside the item (items 3 to 6), and never to flag a missing line or option. Both get the seven items of its prompt (decision `question-reviewer-agent-hook`). The model keeps only what code cannot decide.
- Rule ids. These refuse as `question-form`: a missing Goal, Problem or Based on line, lines out of order, and a Based on count outside one to three. So do a kind outside `PREMISE_KINDS` and an option with no gain or no loss. A Problem line that is bare, or whose stake is outside the set, refuses as `owner-judge` (decision `owner-judge-test`). The older rules keep their ids: `port-question`, `uniform-pick`, `press-link`, `command-in-item`, `gh-login-switch`, `task-names-check`. They run first, in that order, then the form.
- A stood pick and a port carry the full form. A stood pick may omit the stake. A port still needs its Departs from line.
- Update semantics are the page guards' own. An update is judged for the fields it carries (`context`, `options`, `pick`). A closed item passes the form. A `str_replace` on `context` that removes a Goal, Problem or Based on line is refused.
- Text. Rule `style-question-form` in `output-styles/shiv-stylisms.md` holds the form and names `hooks/question_form.py`. The skill `waiting-page` points to that rule.

Risk kind: likely risk, with a named incident. A session writes a question with no problem line or no stated premise in normal work.

Incident:

- 2026-10-30, waiting item 92: a decision with a Goal line and no Problem line, no Based on line, and a widening option not marked `widens`. The old guards passed it.

Landed 2026-10-30.

Cost: no new long-lived process and no file written. `hooks/question_form.py` loads inside the guard process for a waiting-page write, and inside the call judge process for a question box or a page write. Per `ArtifactData` call there is one python start of `call_judge.py`. It exits before any heavy import unless the action is `set`, `update`, `str_replace` or `batch`. It makes one model call (Opus, capped at 60 s) only for an item write on the page that passes `item_hit`. The write carries `options` or `context` (a decision), or `context`, `steps` or `options` (a task). Or it is a `str_replace` on `context` or `options`. A batch makes one call for all its writes, task items included, so a task item in a batch adds no call of its own. A lone task write costs one Opus call; the bound stays one call per `ArtifactData` call. The whole-unit replace rule reaches a task's `steps` and `context` on a set or update. A `str_replace` reaches only the top-level string field `context`. These make no model call: a read, a delete, a write to another collection or page, a receipt or an answer write, and a closed item. So do an `item_hit` hit, a `str_replace` on another field, and an update with none of those fields, such as a title-only write. A call with no write on collection `items` exits before it imports `question_form`. `hooks/test_call_judge.py` proves it. A chat box that fails the code guard makes no model call.

Known limit: code reads words. An unmarked widening option, a false stake and a premise that does not match its kind pass. The question judge model and the reply judge read what code cannot. A `str_replace` is judged on its fragment only, so a fragment cannot be flagged for a line or option it leaves out.

Kind: process
Home: rule:style-question-form
