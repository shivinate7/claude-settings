# Judge prompt: lookalike fence forms are not defanged

- **What.** `_defang` changes only a run of 3 or more ASCII `<` before `BEGIN` or `END` in upper case. Lookalike forms reach the judge intact: a full-width `＜`, a zero-width or soft-hyphen character inside the token, a lower-case `begin`, and a spaced run such as `< < <BEGIN`. The model can read such a form as a fence, so text in an option or a message can pose as an Owner block.
- **Where.** `FENCE_TOKEN` and `_defang` in `hooks/question_outcome.py`.
- **Decision.** `question-outcome-check` (each question passes an outcome check before the owner sees it).
- **Retire.** Fold each lookalike to its ASCII form before the match, and match without regard to case or spaces between the `<`. A test per form shows each prompt holds exactly three Owner blocks.
