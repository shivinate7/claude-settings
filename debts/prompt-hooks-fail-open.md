# A failed prompt hook lets the call through

- **What.** Prompt hooks (Agent, AskUserQuestion, Edit and Write under `decisions/`, SendMessage) can deny, but the docs give them no `onFailure`. A failed prompt hook lets the call through.
- **Where.** The prompt hooks in `settings.json`.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** A failed prompt hook refuses the call through a supported setting, pinned by `hooks/test_wrappers.py`. Or the decision records the accepted risk.
