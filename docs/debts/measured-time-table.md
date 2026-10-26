# No table of measured times for machine steps

**What.** `bin/verdict` logs no kind, seconds and exit per run, and no table keeps measured times. So `style-no-unmeasured-estimate` (no time for agent work without a measured range and its sample count) has no source to cite. Research found that agents misjudge their own task time by 2.6-7x (AgentTime, arXiv 2610.09944); no study shows that history fixes it. Local PR CI takes 8-10 min (13 runs) and main CI 10-15 min (13 runs). The job caps in `.github/workflows/gates.yml` rest on these figures. `pointer-windows`: 27 s, slowest of the last 10 green PR runs on 2026-10-07, before `install-set.test.ps1` joined; that test took 81 s to 156 s on a dev laptop. `shell-macos`: 42 s, same 10 runs. `gates-shoot`: 18 s to 44 s, 4 green runs on 2026-10-26 (dispatch run 40310568830); the Chromium install took 8 s without `--with-deps` and 20 s to 31 s with it. `gates-macos`: 25 min 24 s, slowest of 4 green runs on 2026-10-22 (19.9, 23.8, 24.0, 25.4 min; run 39817425746 was cancelled at the old 25 min cap). The `merge/merge.py` read deadline is shared across calls because a fixed 3 s per call read real `gh` at 3.0-3.9 s as a hang (2026-10-03).

**Where.** `bin/verdict`, and a new table that reads CI times from `gh run list`.

**Decision.** none. The rule `style-no-unmeasured-estimate` in the `shiv-stylisms` output style is the rule half.

**Retire.** Build when the owner asks for the table. `bin/verdict` logs the kind, seconds and exit of each run. The table keeps the last 20 runs per kind and prints each figure with its n and spread. Closed when a figure prints with both.

## Ruling

Owner: no estimates for agent work. Rule now, table later.
