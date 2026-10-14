# Some red and waiting merge states give no remedy

- **What.** A passing check beside runs that all skipped reads red, with no remedy. This is rare: it needs a newest run that skipped under a check that passed. A required name with no entry beside skipped runs holds the wait to the deadline, with no remedy.
- **Where.** `classify` and the wait in `merge/merge.py`.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** Each red or waiting state prints a remedy line, and a case per state pins it.
