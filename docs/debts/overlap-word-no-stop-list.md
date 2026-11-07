# The overlap word clause has no stop list

- **What.** The word clause of rule `lane-start-overlap` (a shared word between a new step and an open lane's step or title) has no stop words. A short shared word, such as `ts`, can ask. Measured: no such hit on the 35 open lanes, 2026-11-07.
- **Decision.** `session-tiers` (the session shapes; the lane-start-overlap bullet).
- **Retire.** The word clause drops stop words before it compares. A case in family `lane-one-topic` shows that a short shared word alone does not ask.
