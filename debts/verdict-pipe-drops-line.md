# A pipe after verdict hides its verdict line

- **What.** `verdict <cmd> | tail` keeps only the last lines, and a wrapper watching the pipe can read a stalled or false exit. On 2026-10-17 an orchestrator's `| tail` on a background merge read as a false exit 3.
- **Where.** `bin/verdict` callers; background Bash commands under the stall watch.
- **Decision.** none
- **Retire.** `bin/verdict` prints its verdict line last and a guard case asks on `verdict ... | tail` in a background command, or the stall watch reads the pipe's first process; a test pins either.
