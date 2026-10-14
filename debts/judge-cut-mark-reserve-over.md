# The cut-mark reserve can push the judge prompt over its bound

- **What.** `fit_span` keeps 37 chars for the cut mark even when no owner message can be cut. The prompt can then go up to 36 chars over `PROMPT_MAX`, and the hook says the check did not run.
- **Where.** `fit_span` in `hooks/question_outcome.py`.
- **Decision.** `question-outcome-check` (the judge checks if a question got its answer).
- **Retire.** Keep the reserve only when a cut can happen. A test with one short owner message and a span over the room fits within `PROMPT_MAX`.
