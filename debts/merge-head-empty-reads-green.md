# The wait reads green with no checks and no runs

- **What.** With no required names, zero checks and zero runs, the wait reads green after its 30 s settle. The read says pending. This predates the proven-head rule.
- **Where.** The wait in `merge/merge.py`.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** The wait refuses on zero checks and zero runs, and a case pins it.
