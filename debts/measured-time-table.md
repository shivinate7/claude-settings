# No table of measured times for machine steps

**What.** `bin/verdict` logs no kind, seconds and exit per run, and no table keeps measured times. So `style-no-unmeasured-estimate` (no time for agent work without a measured range and its sample count) has no source to cite. Research found that agents misjudge their own task time by 2.6-7x (AgentTime, arXiv 2610.09944); no study shows that history fixes it. Local PR CI takes 8-10 min (13 runs) and main CI 10-15 min (13 runs).

**Where.** `bin/verdict`, and a new table that reads CI times from `gh run list`.

**Decision.** none. The rule `style-no-unmeasured-estimate` in the `shiv-stylisms` output style is the rule half.

**Retire.** Build when the owner asks for the table. `bin/verdict` logs the kind, seconds and exit of each run. The table keeps the last 20 runs per kind and prints each figure with its n and spread. Closed when a figure prints with both.

## Ruling

Owner: no estimates for agent work. Rule now, table later.
