# waiting-on-template-passes

**What.** The check accepts the copied template: a `Waiting on: <what is stopped until your answer>; <who acts next>` line, or a `why` of `<the one-line reason>`, passes as filled. The Goal, Problem and Based on lines refuse a placeholder, so the new lines are the one gap. The remedy text prints that exact template, so a session may copy it.

**Where.** `hooks/question_form.py`: `waiting_filled` and `recommendation_miss`. `placeholder_form_hit` is the check that refuses a placeholder on the other lines.

**Decision.** `question-form` (one form and one guard for the chat box and the page).

**Retire.** Make `waiting_filled` and `recommendation_miss` refuse a text that is only an angle-bracket placeholder, as `placeholder_form_hit` does, with a red case first. Shown closed by `hooks/test_question_form.py`.
