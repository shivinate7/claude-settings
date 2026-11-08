# A relative write after an absolute cd out of the home is refused

**What.** The relative-write clause resolves a relative target against the folder its segment runs in, after a leading `cd`. When that `cd` names an absolute folder outside the agent's recorded home, the write is refused under worktree-home: `cd <scratchpad> && mkdir probe`, `cd /tmp && mkdir x`, `cd <scratchpad>; echo x > out.txt`, `cd <scratchpad> && cp a b`. Main allowed all four. The same write by absolute path passes, so the refusal closes no hole. No override lifts it, and the reason tells the agent to stop. A builder or test-author that works in its scratchpad with `cd <scratchpad> && ...` hits it in normal work.

**Where.** `hooks/guard.py`, `relative_write_escape`: the target resolves against `dir_before_segment`, with no check that the leading `cd` itself left the home by an absolute path.

**Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its home tree must stop).

**Retire.** A relative write whose leading `cd` names an absolute, `~` or variable path is not judged by this clause, as an absolute target is not. `cd <scratchpad> && mkdir probe` allows, and `mkdir ../tmp` and `cd sub && mkdir ../../x` from the home still deny. Rows in `hooks/test_guard.py`, family "relative escape", show both.
