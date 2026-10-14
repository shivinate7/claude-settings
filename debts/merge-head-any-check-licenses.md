# Any passing check licenses a skipped required job

- **What.** Any passing check licenses a skipped required job, not only `scope`. The tool does not check which check passed.
- **Where.** The required-job check in `merge/merge.py`.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** The tool licenses a skipped job only from its named check, and a case pins it.
