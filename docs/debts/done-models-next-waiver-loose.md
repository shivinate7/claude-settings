# Next waiver in the model-name check reads any role word

- **What.** The report guard waives "no model named for <role>" when the report's Next names that role. It keys on the role word, not on a spawn that is still running. A finished reviewer goes unnamed in Done when Next says "send a fresh reviewer for round 2" or lists the role under Unstarted. Review rounds hit this in normal work. The harm is one missing model line; the spawn guard still holds the cap.
- **Where.** `done_models_problem` in `lint/report_guard.py`.
- **Decision.** `agent-model-cap` (the model-per-role table); rule `reports-done-names-models`.
- **Retire.** Waive only a spawn whose agent has no result or finish notice in the transcript, with a case that a finished reviewer named only in Next blocks.
- **Fix.** `step:next-waiver-scope`.
