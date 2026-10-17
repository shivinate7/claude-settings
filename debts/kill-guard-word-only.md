# The kill guard reads one word

- **What.** `kill_hit` reads only the command word. `gtimeout 5 pkill -f node` and `watch pkill` pass.
- **Where.** `hooks/guard_kill.py`.
- **Decision.** `guard-reads-wrapped-commands` (the stream and delete guards read the command a wrapper runs).
- **Retire.** Use `inner_commands` or `bare_words` in the kill guard.
