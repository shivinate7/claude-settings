# Other rules read the first -C target in a command

- **What.** The discard rule judges each git call in its own checkout. Other rules that read the run folder take the first `-C` in the command. Their verdict or citation can name the wrong checkout. No discard depends on that read.
- **Where.** The run-folder read in `hooks/guard_shared_tree.py`, used by rules other than the discard rule.
- **Decision.** `agent-worktree-discard-is-noted` (a discard or remove in a worktree).
- **Retire.** Each rule reads the run folder of its own git call. A test with two `-C` targets pins the citation for each rule.
