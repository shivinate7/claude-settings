# The wording judge still runs on every send

- **What.** The SendMessage prompt hook in `settings.json` runs a model call on every send. The state judge removes none of those calls.
- **Where.** The SendMessage prompt hook in `settings.json`.
- **Decision.** `subagent-model-cap` (model per role; holes for the SendMessage state judge).
- **Retire.** Rule whether the state judge replaces the wording judge for idle and waiting receivers. If it does, narrow the prompt hook, and show a send to an idle receiver makes one model call less.
