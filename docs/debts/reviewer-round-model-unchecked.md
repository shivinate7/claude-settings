# A round 2 or 3 reviewer can run on haiku

**What.** The role-model check refuses a reviewer on sonnet when its brief has no `Round N of 3`
first line. The refusal's remedy names only "drop the model field, or name the role's model".
For a reviewer, the role's model is haiku, so the remedy points a later-round reviewer to haiku.
Lane renovate-917-918 ran its round-2 and round-3 reviewers on haiku on Nov 1. The check reads
the role, not the round, so haiku passes it. Evidence: Nov 1, lane impeccable-4.8.0 (commit
70b65a10). That reviewer was re-run on sonnet.

**Where.** `hooks/guard.py`: `ROLE_MODEL_REASON` (the refusal text) and `role_model_check`
(guard rule `agent-role-model`, the role-model check).

**Decision.** `agent-model-cap` (the model per role).

**Retire.** The refusal names the `Round N of 3` first-line marker and the rounds that allow it,
read from `ROLE_REVIEWER_FREE_ROUNDS`. A `test_guard.py` role-model case asserts it: red on main,
green on the fix.
