# The question judge reads only the ruling headings it knows

- **What.** Rulings under another heading are not read.
- **Where.** `RULING_HEADING` in `hooks/question_outcome.py`.
- **Decision.** `question-judge-reads-rulings` (the question judge refuses a question the owner already settled).
- **Retire.** Each heading form a decision record uses is read, and a test pins the list of forms.
