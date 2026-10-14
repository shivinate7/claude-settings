# The question judge leaves out the oldest rulings past its cap

- **What.** Measured 2026-10-14 (review round 1): 87 rulings, 100,887 chars uncapped. With the cap at 60,000 chars, 5 of the 87 do not fit and are left out, oldest first. The live model call took 11 s of the 90 s budget.
- **Where.** `RULINGS_MAX` in `hooks/question_outcome.py`.
- **Decision.** `question-judge-reads-rulings` (the question judge refuses a question the owner already settled).
- **Retire.** A full set of rulings fits the budget, measured on the live call. A test pins that no ruling is left out.
