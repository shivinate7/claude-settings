# The session key line is copied

- **What.** The session key line is copied from `decision_watch._seen_store_path`, with no stated reason. The rule `building-one-home-per-capability` asks for a stated reason. The key line lives in two places.
- **Where.** The session key line in the Stop reply judge hook.
- **Decision.** `haiku-prompt-hooks` (haiku prompt hooks, Stop reply judge).
- **Retire.** One shared helper that both hooks call. A grep finds one key line.
