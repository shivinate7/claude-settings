# In gh, a session number after -m passes the lane rule

- **What.** In gh, `-m` is a milestone or merge flag, never a message. `gh pr create -m N20` is allowed, so a session number in that flag passes the rule.
- **Where.** The lane-slug message readers, for the gh `-m` flag.
- **Decision.** `lane-by-slug` (lanes are named by slug, and records are cited by id).
- **Retire.** The owner rules whether `gh pr create -m N20` is allowed. A test pins the verdict for that command.
