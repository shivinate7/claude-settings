# A human message between the phases moves the verdict baseline

- **What.** A new human message between the two phases moves the baseline. A real FLAG then prints `verdict lost`. The output is loud and correct, and the README names this cause.
- **Where.** The baseline check in `hooks/decision_watch.py`.
- **Decision.** `decision-watch-mod-limits` (the mod judges each Stop in the background and never blocks).
- **Retire.** The verdict text names the cause, not only the README. A test pins that text for a human message between the phases.
