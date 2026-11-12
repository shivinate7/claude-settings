# A bare file name with no extension names nothing

**What.** A bare file name with no `/` and no extension, such as `Makefile`, `Dockerfile` or `LICENSE`, names no path. Neither does a dotfile whose name runs over ten characters after the dot, such as `.dockerignore`. A brief that names one of these beside another path has that file's change refused, with no override. A brief that names only that file is logged as unnamed and allowed. A path such as `src/Makefile` still counts. Builders edit such files in normal work, and other repos likely have them, so Claude is likely to hit it.

**Where.** `hooks/guard.py`, `BRIEF_EXT` (the extension test) and `BriefScope.add` (the bare-name branch).

**Decision.** `agent-commit-file-scope` (an agent's commit touches only the files its brief names).

**Retire.** Closed when a case in `hooks/test_guard.py` (family `brief-scope`) allows a change to a `Makefile` that the brief names beside another path.
