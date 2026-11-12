# An untagged owner-started coordinator passes the lone-lane rule

**What.** A coordinator the owner started, with no `cs-build:coordinator` tag, has no parent session and no `cs-build:` tag. The lone-lane rule reads only those two facts, so it admits that session's `merge --role batch-runner` call and its confirm. The confirm is admitted only in claude-settings, because the record's sources must name it. A coordinator never merges (owner, 2026-11-01 21:34 CST). Coordinator pick, 11:22 CST Nov 12: file as a debt, not a new check. The premise, that a lane a coordinator started has a parent, is measured on one case (n=1), so it is unmeasured beyond that case.

**Where.** `hooks/guard_merge.py`: `_lone_shape` and `_lone_lane_proved` (the role proof), and the lone-lane branch of `_unproved_confirm` (the confirm check).

**Decision.** `standing-merge-grant`, its lone-lane Role sub-bullet (the record shape the rule reads).

**Retire.** Add a case to the merge section of `tests/guard/s13406-merge.py`, which `hooks/test_guard.py` runs. The case is a record with no parent, no `cs-build:` tag and a source that names claude-settings, with a `merge --role batch-runner` call that expects a refusal. It is red while the rule admits it.
