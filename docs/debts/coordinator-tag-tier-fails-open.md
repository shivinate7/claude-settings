# Coordinator tier fails open until get_session

- **What.** Nothing writes a coordinator role file, because `MERGE_ROLES` holds only `batch-runner` and the coordinator runs no `--role` call. So a coordinator's tier comes only from its own `cs-build` tag in a `get_session` result in the transcript. Until the coordinator runs `get_session` on itself, and after `/clear` or with an unreadable transcript, `_own_tag_tier` returns `''` and rule coordinator-scope never fires.
- **Where.** `_own_tag_tier` and `_cloud_coordinator` in `hooks/guard.py`; `MERGE_ROLES` in `hooks/shared_names.py`; the coordinator role and brief templates in `skills/project-ops`, which do not tell a coordinator to run `get_session` on itself at start.
- **Decision.** `session-tiers` (the session shapes and their tier guards).
- **Retire.** A coordinator's tier holds from its first judged call, with no `get_session` result in the transcript. Or the coordinator's start steps run `get_session` first, and a case proves the rule fires then. `hooks/test_guard.py` holds that case.
