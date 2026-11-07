# A one-install profile reads every known defect UNKNOWN when its install fails

- **What.** A profile with one install (joyous) has no part regex to route by, so a failed install makes every defect need it, and every defect reads UNKNOWN and the job red.
- **Where.** `hooks/mutate_shared.py` `run_known_defects` and `_needed_parts`.
- **Decision.** mutation-ci-report-and-replay (the known-defect replay reads an install that fails as UNKNOWN).
- **Fix.** none — rare and harmless. A failed install of the one install is a real outage of the package source, and a red job is the right signal.
- **Until.** Until a one-install profile names a catcher that needs no install, or an install failure there costs a merge.
- **Retire.** A case in `hooks/test_mutate_ci.py` where a one-install profile's install fails and an install-free catcher still reads CAUGHT goes red on the old code, then green.
