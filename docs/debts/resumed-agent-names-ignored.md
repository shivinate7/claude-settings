# A resumed agent's later names are ignored

**What.** `brief_text` reads only the first user message of an agent's transcript as its brief. A later message adds no names. So when a resumed agent changes an existing file that only its resume message names, the guard refuses the change at commit, push and the first stop, with no override. A second stop is released (`brief-scope-unresolved`), so the agent can end, but its change cannot be committed or pushed. The rule `roles-resume-by-name` resumes a dead agent by name, so Claude hits this in normal work.

**Where.** `hooks/guard.py`, `brief_text` (reads the first user record only) and `brief_scope_hit` (judges the change against those names).

**Decision.** `agent-commit-file-scope` (an agent's commit touches only the files its brief names).

**Retire.** Closed when the decision states how a resumed agent's later names are judged, and a case in `hooks/test_guard.py` (family `brief-scope`) shows that judgement.
