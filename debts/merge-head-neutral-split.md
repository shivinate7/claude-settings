# A neutral run reads red in one check and green in another

- **What.** `neutral` reads red in `classify` and green in `judge_runs`. This split predates the proven-head rule.
- **Where.** `classify` and `judge_runs` in `merge/merge.py`.
- **Decision.** `merge-needs-a-proven-head` (a head is proven only after a check passes on it).
- **Retire.** Both functions read `neutral` the same way, and a case pins it.
