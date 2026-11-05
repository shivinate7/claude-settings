# Each batch reports its mutation catch share and replays known defects

## The ruling

Owner, 2026-11-05 07:41 CST (waiting-page item 163, Cockpit item `mutation-ci-job`, pick d): "Report only, plus known-bug replay". Note with the pick: "we also reopen this in a while after logging for a bit".

The shared action `actions/mutation-report` runs on each batch's integration pull request (head ref `batch-*`) and on workflow_dispatch. It has two steps:

- **Report.** `hooks/mutate_guard.py --changed` mutates only the product lines the batch added (merge base to head). Each mutated file runs every suite that the profile's `select` lists for it, changed or not. The step prints the catch share (killed over ran; a crash is not a kill) and one `untested: path:line` line per line whose mutant survived or reached no suite. It exits 0 whatever the share. A low share never fails the job.
- **Known-defect replay.** `hooks/mutate_guard.py --known-defects .github/known-defects.json` re-plants each named past defect in a copy of the head tree and runs the suite named to catch it. CAUGHT needs an assertion red. A green run or a crash is MISS. A red clean run, or a plant text that is missing or not unique, is UNKNOWN. A MISS or an UNKNOWN fails the job.

The modes are part of the one home of mutation testing (`hooks/mutate_guard.py` with `hooks/mutate_shared.py`, decision `mutation-report-scores-suites`). `replay_pr` keeps its changed-suites-only default.

## Why a replay miss fails the job

A replay miss means that a test which once caught a real defect no longer catches it. The two named incidents were such losses: 3297d8fa (a lane deleted the test that pinned merge.py's ten-minute lock spare) and df25a68d (a fix deleted the tests that pinned its own two fixes). The suites that catch them are back on main, and the replay keeps them there.

Evidence, 2026-11-05, main 0497265b, each plant applied by hand in a copy of the tree:

| Defect | Catcher | Clean runs | Planted runs | Gold |
|---|---|---|---|---|
| `df25a68d-rlock`: `_LIVE_LOCK` back to `threading.Lock()` | `hooks/test_mutate_replay.py RequestStopTests` | 3 green | 3 red, assertion | 3 red |
| `df25a68d-pw-timeout`: the timeout and closed-target test dropped from `classify_playwright` | `hooks/test_mutate_replay.py PlaywrightClassifyTests` | green | 3 red, assertion (87-90 s, whole file) | 3 red |
| `3297d8fa-take-spare`: `+ 10` dropped from the lock take call | `merge/test_merge.py LockProseStatesTheCode` | 1 green | 3 red, assertion | 3 red |

Every run was the same, and none needed the network. A fixture suite in `hooks/test_mutate_ci.py` proves that a catcher which pins nothing reads MISS. So a red replay names a lost test, not a flake. An UNKNOWN is red under decision `ci-unknown-is-red`. A plant text that a refactor moved is re-pointed in `.github/known-defects.json`, red then green (`outcomes-tests-are-statements`).

The silent-undo check (`lint/check_silent_undo.py`) does not see these losses. Its read of the two batches that landed them (PRs 1082 and 1075) flagged other files only. The waiting item `no-undo-net-loss-dial` holds the read that would.

## The log

Each run uploads one artifact, `mutation-report`, with two JSON files: the report (base, head, profile, made, killed, crashed, survived, not_run, untested) and the replay verdicts. The job summary shows the catch share and the untested lines. GitHub keeps artifacts 90 days by default.

Reader: the owner, when item 163 is reopened. The read is on demand: `gh run list --workflow checks.yml --branch <batch>` and then `gh run download <run> -n mutation-report`. Nothing commits a log to the repo.

## Cost

Measured locally, 2026-11-05, on batch 11 (59bff081 to 0497265b), 4 cores, with the job's settings: 10 mutants, a 300 s budget, a 180 s suite timeout. The range changed one product file, `hooks/stall_watch.py`.

| Step | Wall time | Process starts | Files written | Target |
|---|---|---|---|---|
| `--changed` | 337 s; 326 s on a rerun | 75 direct (26 git, 49 suite or select runs) | 4 temp checkouts of 905 files and 49 run files, all removed; one JSON log | under the cap |
| `--known-defects` | 7 s, 3 of 3 CAUGHT | one checkout and 2 suite runs per defect | temp checkouts, removed; one JSON log | under the cap |

The job cap is 15 minutes: about 2 times the 7 minutes of these steps and the setup. The CI minutes of the first batch run replace this figure (decision `ci-job-caps`). The cost per batch grows with the product lines the batch adds, up to the budget per change.

The share moves with the sample, the budget and the load of the machine. The same range read 4 of 10 killed (6 untested lines), then 1 of 5 with 5 not run on a loaded rerun. Read a share as "a gap exists", not as an exact figure. A file whose suite is not a `test_<stem>` file beside it reads untested, such as the replay code in `hooks/mutate_shared.py`.

A test in `hooks/test_mutate_ci.py` proves that each mode writes only its `--log` file and leaves the repository as found.

## Adoption

claude-settings first. Each child repo adopts the action in its own lane. q_max and banchi have profiles and per-file selectors already. Each needs the action pin, a checkout with `fetch-depth: 0`, and a `.github/known-defects.json`. degen, mailaudit, home, ios-adblock and joyous also need a profile and a selector.

Kind: process
Home: hooks/mutate_shared.py
