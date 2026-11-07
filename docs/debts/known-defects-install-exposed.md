# A failed install turns defects UNKNOWN that may not need it

- **What.** A profile with one install (`joyous`, `q_max`, `mailaudit`, `degen`) has no part to route by, so a failed install makes every defect UNKNOWN. In `banchi` and `ios_adblock`, a defect that no part claims needs every install, so one failed install does the same.
- **Where.** `hooks/mutate_shared.py` `run_known_defects` and `_needed_parts`; the profiles are in `REPLAY_PROFILES` in `hooks/mutate_guard.py`.
- **Decision.** mutation-ci-report-and-replay (the known-defect replay reads a defect that needs a failed install as UNKNOWN).
- **Fix.** none — rare and harmless. A failed install is an outage of the package source, and a red job is the right signal.
- **Until.** A failed install in one of these profiles costs a merge, or an entry in `.github/known-defects.json` needs no install.
- **Retire.** A way to tell an install-free defect from one that needs the install, built with a case that goes red on the old code. Today `hooks/test_mutate_ci.py` pins the exposure (a one-install profile reads every defect UNKNOWN); the fix re-points that case, and the debt closes when the file is green.
