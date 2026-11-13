# A git option other than -C is not read, so a git write into another checkout passes

**What.** An agent can write into another checkout by mistake with `git --work-tree=<sibling> commit` or `git --git-dir=<sibling>/.git commit`. The guard reads only `-C` for the folder a git verb runs in, so the write passes. The harm: a commit or index change lands in a checkout the agent does not own.

**Where.** `hooks/guard.py`, `session_home_git_hit`, and `_segment_git_c_target` in `hooks/guard_core.py`.

**Decision.** `an-agent-outside-its-home-tree-must-stop`, an agent outside its home tree must stop (`other-checkout`).

**Retire.** Read `--work-tree=` and `--git-dir=` as the folder a git verb runs in, and judge it as `-C` is judged. Closed when `hooks/test_guard.py` holds a red case that refuses each form for an agent.
