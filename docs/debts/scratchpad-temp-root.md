# The scratchpad test assumes the temp folder

- **What.** `under_session_scratchpad` passes a path only when it sits under `tempfile.gettempdir()`. On macOS that is `$TMPDIR` (`/var/folders/...`). A Claude Code scratchpad may sit under `/tmp/claude-<uid>/`. If so, the scratchpad pass of `other-checkout` never applies on a Mac, and its false alarm stays. The two other rules that call the same test lose their pass too. Unmeasured on a Mac.
- **Where.** `hooks/guard_shared_tree.py` `under_session_scratchpad` and `in_any_session_scratchpad`; the rules `other-checkout`, shared trees, and test-author writes in `hooks/guard.py`.
- **Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its home tree must stop), the premise line of `other-checkout`.
- **Retire.** A session on a Mac prints its scratchpad path and `tempfile.gettempdir()`. If the first sits outside the second, the test reads the scratchpad root the harness uses, and a test case covers a `/tmp/claude-<uid>/` root.
