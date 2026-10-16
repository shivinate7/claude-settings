# An escaped space refuses the move home

**What.** The worktree-home rule refuses a lone `cd` back into the home when the path has a
space escaped with `\`, a trailing newline, or one of `&`, `;`, `(`, `)` or `$`. The refusal
fails closed: the agent stops and reports.

**Where.** `hooks/guard_core.py`, `is_move_into`.

**Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its tree stops).

**Retire.** `is_move_into` reads the path with the shell's own tokenizer. A test_guard.py
case moves into a home with an escaped space and is allowed.
