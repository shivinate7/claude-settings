# A failed install turns defects UNKNOWN that may not need it

- **What.** A profile with one install (`joyous`, `q_max`, `mailaudit`, `degen`) has no part to route by, so a failed install makes every defect UNKNOWN. In `banchi` and `ios_adblock`, a defect that no part claims needs every install, so one failed install does the same.
- **Where.** `hooks/mutate_shared.py` `run_known_defects` and `_needed_parts`; the profiles are in `REPLAY_PROFILES` in `hooks/mutate_guard.py`.
- **Decision.** mutation-ci-report-and-replay (the known-defect replay reads a defect that needs a failed install as UNKNOWN).
- **Fix.** none — unmeasured; no live profile in this repo has an install.
- **Measured when.** A repository that has an install runs the replay in CI, and a failed install there costs a merge.
- **Retire.** A way to tell an install-free defect from one that needs the install. Closed when `hooks/test_known_defects_exposed.py` exists and holds a case that goes red on the code before the fix and green after it. The file does not exist yet.
