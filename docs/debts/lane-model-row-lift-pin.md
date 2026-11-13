# Override lift of the lane model row has no log check

- **What.** Rule `lane-start-settings` refuses a lane whose model is outside its row's family (`lane_model_row_hit`). A typed owner override lifts it. No case pins that lift, because a log check for it needs a `LOG_CHECKS` entry, and that table waits for the lane that splits it per section.
- **Where.** `hooks/guard.py`, `lane_model_row_hit` and its refusal at step 9b2c. `hooks/test_guard.py`, `LOG_CHECKS`.
- **Decision.** `agent-model-cap` (agent model cap, the model per role).
- **Retire.** A `LOG_CHECKS` entry pins that an owner override lifts the `lane_model_row_hit` refusal, and `hooks/test_guard.py` passes with it. Fix: step:guard-tables-per-section (guard tables per section).
