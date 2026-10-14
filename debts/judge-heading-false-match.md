# The ruling heading pattern matches "Ruling out" headings

- **What.** The ruling-heading pattern also matches a heading such as "Ruling out ...", so a heading that is not a ruling is read as one.
- **Where.** `RULING_HEADING` in `hooks/question_outcome.py`.
- **Decision.** `question-judge-reads-rulings` (the question judge refuses a question the owner already settled).
- **Retire.** The pattern matches only the ruling heading forms, and a test pins that a "Ruling out ..." heading is not read.
