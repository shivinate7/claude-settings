# The unreadable-folder test runs on POSIX only

- **What.** The unreadable-folder exit 2 test runs only on POSIX. The symlink case did not run on Windows.
- **Where.** The fixture suite for `lint/check_skill_model_rows.py`.
- **Decision.** `subagent-model-cap` (the subagent model cap, and its skill rows check).
- **Retire.** Run the exit 2 test and the symlink case on Windows. Both verdicts are recorded.
