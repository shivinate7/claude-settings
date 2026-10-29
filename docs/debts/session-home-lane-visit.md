# A visit to a lane tree becomes the session's home

- **What.** A top-level session whose `cwd` enters a non-agent lane tree gets a session-home record naming it, and a return to the primary does not clear it. Once that tree is removed, its primary writes and commits are refused as "worktree is gone", though it never lived there.
- **Where.** `hooks/guard.py` `session_home_keep`, rule `session-home`.
- **Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its home tree must stop).
- **Retire.** A call that arrives in the primary while the record's folder still stands drops the record. A red-then-green case in `hooks/test_guard.py`: cwd in a lane tree, then a primary call, then the tree removed, then a primary Write passes.
