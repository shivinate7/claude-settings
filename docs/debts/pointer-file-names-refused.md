# A brief's named brief file is read as a pointer

**What.** Seven tracked files have `brief` in their name and end `.md`, such as `docs/decisions/brief-destructive-git.md`. The guard reads a file a brief names as a pointer: it adds the file's text to the brief's names and skips the file's own name. So a brief that names one of these records for edit, beside another path, has that record's change refused at commit, push and stop. A brief that names only that record is logged as unnamed and allowed. Writing a brief to edit one of these records is normal work, so Claude is likely to hit it.

**Where.** `hooks/guard.py`, `is_pointer` and `brief_pointer` (a pointer's own name is skipped), and `BriefScope.__init__` (the skip list).

**Decision.** `agent-commit-file-scope` (an agent's commit touches only the files its brief names).

**Retire.** Closed when a case in `hooks/test_guard.py` (family `brief-scope`) allows a change to a `*brief*.md` file that the brief names, beside another named path.
