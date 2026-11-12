# A brief's weak names refuse every existing-file change

**What.** A brief with no real path but `e.g.` or `i.e.` counts as naming, since those read as bare names (`e.g`, `i.e`). So does a brief that cites only `README.md` or `CLAUDE.md`, since a bare file name matches a file of that name at any depth. Such a brief is not logged as unnamed. Every existing-file change outside those names is refused. The exceptions are a file whose name equals the bare name, at any depth, and the generated pages. Briefs often cite `README.md`, and `e.g.` is common prose, so Claude is likely to hit this.

**Where.** `hooks/guard.py`, `BriefScope.add` (a bare name with an extension counts as named).

**Decision.** `agent-commit-file-scope` (an agent's commit touches only the files its brief names).

**Retire.** Closed when a case in `hooks/test_guard.py` (family `brief-scope`) logs `brief-scope-unnamed` for a brief whose only names are `e.g.` or `README.md`, and the decision's limit on them is rewritten.
