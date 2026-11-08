# No table of measured times for machine steps

**What.** `bin/verdict` logs no kind, seconds and exit per run, and no table keeps measured times. So `style-no-unmeasured-estimate` (no time for agent work without a measured range and its sample count) has no source to cite. Research found that agents misjudge their own task time by 2.6-7x (AgentTime, arXiv 2610.09944); no study shows that history fixes it. Local PR CI takes 8-10 min (13 runs) and main CI 10-15 min (13 runs). The job caps in `.github/workflows/checks.yml` rest on these figures. `pointer-windows`: 27 s, slowest of the last 10 green PR runs on 2026-10-07, before `install-set.test.ps1` joined; that test took 81 s to 156 s on a dev laptop. `shell-macos`: 42 s, same 10 runs. `checks-shoot`: 18 s to 44 s, 4 green runs on 2026-10-26 (dispatch run 40310568830); the Chromium install took 8 s without `--with-deps` and 20 s to 31 s with it. `checks-macos`: 25 min 24 s, slowest of 4 green runs on 2026-10-22 (19.9, 23.8, 24.0, 25.4 min; run 39817425746 was cancelled at the old 25 min cap); 37.1 min slowest of 15 green runs (median 31.1) from 2026-11-01 to 2026-11-02, so its cap is now 55 min. `shell-macos`: about 19.2 min slowest of 18 runs (16 green, 2 cap ends, run 41407916830 at 18.07 min and run 41407758669 at about 19.2 min; median 12.27) from 2026-11-01 to 2026-11-02, so its cap is now 28 min. Run 41730427997 (workflow dispatch on main, full suite, 2026-11-03) took `checks-macos` 40.6 min and `checks` 33.4 min, the two slowest jobs, so each was split in 2. After the split, from 2026-11-05 to 2026-11-06, the slowest green runs were 30.5 and 21.5 min (`checks-macos`, checks-macos-b) and 22.8 and 20.6 min (`checks`, checks-merge-install). The per-job table of 30 runs is in decision `ci-job-caps`. The `merge/merge.py` read deadline is shared across calls because a fixed 3 s per call read real `gh` at 3.0-3.9 s as a hang (2026-10-03).

**Where.** `bin/verdict`, and a new table that reads CI times from `gh run list`.

**Decision.** `ci-job-caps` holds the job table. The rule `style-no-unmeasured-estimate` in the `shiv-stylisms` output style is the rule half.

**Retire.** Build when the owner asks for the table. `bin/verdict` logs the kind, seconds and exit of each run. The table keeps the last 20 runs per kind and prints each figure with its n and spread. Closed when a figure prints with both.

## Ruling

Owner: no estimates for agent work. Rule now, table later.
