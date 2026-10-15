# The question judge cuts a long ruling at 800 chars

- **What.** A ruling over 800 chars is cut at a sentence end, so a settled point late in a long ruling may be missed.
- **Where.** `RULING_CAP` in `hooks/question_outcome.py`.
- **Decision.** `question-judge-reads-rulings` (the question judge refuses a question the owner already settled).
- **Retire.** A test puts a settled point after the 800-char cut and pins that the judge still reads it.
