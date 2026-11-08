# A fix-round brief that names a commit before its goal asks

**What.** A builder brief such as `make the red cases in hooks/test_guard.py from commit 9e7a8fa31 pass` asks at spawn, because the goal word falls outside the three-word window after the path. Every fix-round builder brief that anchors a commit hits it.

**Where.** `hooks/guard.py`, `_message_goal`: the window after the path.

**Decision.** message-role-scope (what a message or brief edits).

**Retire.** `_message_goal` reads a goal past a `from commit <sha>` or `(commit <sha>)` anchor. A case in `hooks/test_guard.py` passes that builder brief and still asks on `make the red cases in X fail`.
