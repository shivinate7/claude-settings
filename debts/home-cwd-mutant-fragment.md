# home_cwd mutants name no case

**What.** The four `home_cwd` mutants require only the fragment `worktree-home:`. Any
worktree-home case kills them, so a kill does not prove the named case.

**Where.** `hooks/mutate_guard.py`, the four mutants whose anchor holds `home_cwd`.

**Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its tree stops).

**Retire.** Each mutant names its own test case. The harness shows each one killed by that
case.
