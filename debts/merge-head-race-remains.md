# The push-to-ready race remains

- **What.** The race between a push and `gh pr ready` remains. Mark a PR ready only after its push run exists, or dispatch the workflow by hand. The tool refuses now. It does not dispatch.
- **Where.** `merge/merge.py`, the head proof.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** The tool dispatches the workflow for a head with no runs, and a case pins it.
