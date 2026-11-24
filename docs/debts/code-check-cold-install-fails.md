# A cold install that cannot start still refuses the ready mark

**What.** A pinned tool that cannot start, such as a pipx or npx install with no route to the index, reads unknown. A ready run still refuses an unknown: `run_ready_checks` stops on any state but pass, and no flag lifts it. So a session with no registry access cannot mark a draft ready until the registry answers.

**Where.** `merge/merge.py`, `run_ready_checks()` (about :5388-5400), the stop on a state other than pass ("are unknown, not a pass").

**Decision.** `lanes-run-no-full-ci-job` (the ready checks; a run that cannot start reads unknown). The owner has not ruled whether a ready mark may pass on that unknown.

**Retire.** `lint/test_cheap_lints.py` gets a red case: a ready run whose pinned tool cannot start, with no route to the index, leaves a session with no registry access a route to ready, as the owner rules.
