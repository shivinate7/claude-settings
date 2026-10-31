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
- Code checks the lines, their order and the marks. `hooks/question_form.py` is the one home: `item_hit` for a page write, `chat_hit` for a chat box. `hooks/guard.py` calls `item_hit` after its url and collection guard. `hooks/call_judge.py` calls `chat_hit` before any model call, and refuses with the rule it names. The question judge model keeps only what code cannot decide: the seven items of its prompt (decision `question-reviewer-agent-hook`).
- Rule ids. These refuse as `question-form`: a missing Goal, Problem or Based on line, lines out of order, and a Based on count outside one to three. So do a kind outside `PREMISE_KINDS` and an option with no gain or no loss. A Problem line that is bare, or whose stake is outside the set, refuses as `owner-judge` (decision `owner-judge-test`). The older rules keep their ids: `port-question`, `uniform-pick`, `press-link`, `command-in-item`, `gh-login-switch`, `task-names-check`. They run first, in that order, then the form.
- A stood pick and a port carry the full form. A stood pick may omit the stake. A port still needs its Departs from line.
- Update semantics are the page guards' own. An update is judged for the fields it carries (`context`, `options`, `pick`). A closed item passes the form. A `str_replace` on `context` that removes a Goal, Problem or Based on line is refused.
- Text. Rule `style-question-form` in `output-styles/shiv-stylisms.md` holds the form and names `hooks/question_form.py`. The skill `waiting-page` points to that rule.

Risk kind: likely risk, with a named incident. A session writes a question with no problem line or no stated premise in normal work.

Incident:

- 2026-10-30, waiting item 92: a decision with a Goal line and no Problem line, no Based on line, and a widening option not marked `widens`. The old guards passed it.

Landed 2026-10-30.

Cost: no new process and no file written. `hooks/question_form.py` loads inside the guard process for a waiting-page write, and inside the call judge process for a question box. A chat box that fails the code guard makes no model call, so a refusal costs less than before.

Known limit: code reads words. An unmarked widening option, a false stake and a premise that does not match its kind pass. The question judge model and the reply judge read what code cannot.

Kind: process
Home: rule:style-question-form
