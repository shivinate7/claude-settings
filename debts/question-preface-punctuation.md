# A punctuation-led preface line before Goal is denied

- **What.** A punctuation-led preface line before `Goal:`, such as `- problem: note`, is denied. The denial is correct, but the free pass then lets the retry through.
- **Where.** The order check in `hooks/question_outcome.py`.
- **Decision.** `question-outcome-check` (each question passes an outcome check before the owner sees it).
- **Retire.** A test pins the denial. The owner rules whether a retry passes without a check.
