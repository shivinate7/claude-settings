# A Plan or review brief that quotes a builder task is denied

- **What.** A Plan, refuter or reviewer brief is refused for a builder task it quotes. Examples: "Put the new helper in hooks/lib.py", "Plan step 3: Save the result to .claude/state.json", "You may create a file only in your scratchpad, never in the repo". The reader ignores the destination and a trailing negator.
- **Where.** `hooks/guard.py` `brief_write_hit`, the prose pass.
- **Decision.** `brief-write-needs-writer` (a read-only agent's brief never orders a file write).
- **Retire.** The reader judges the order's subject, the agent being briefed, not a task it quotes. For "create a file" it reads the destination and any negator. A case in the `brief-write-needs-writer` family in `hooks/test_guard.py` checks it.
