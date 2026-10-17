# The exemption list is shared

- **What.** The search-tool exemption in `bare_words` uses `ENV_PATTERN_COMMANDS`, which the env-file rule also uses. A tool added for one rule changes both.
- **Where.** `hooks/guard_core.py`.
- **Decision.** `guard-reads-wrapped-commands` (the stream and delete guards read the command a wrapper runs).
- **Retire.** Give the exemption its own list, or pin the coupling in a test.
