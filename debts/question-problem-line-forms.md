# Some Problem line forms do not count

- **What.** `1. Problem:` (digit prefix) and `Problem :` (space before the colon) do not count as Problem lines. Each passes presence only with a second plain `Problem:` line. It then passes the order check even before `Goal:`.
- **Where.** The label readers in `hooks/question_outcome.py`.
- **Decision.** `question-outcome-check` (each question passes an outcome check before the owner sees it).
- **Retire.** Both forms are read as Problem lines, and a case per form is denied when `Goal:` comes later.
