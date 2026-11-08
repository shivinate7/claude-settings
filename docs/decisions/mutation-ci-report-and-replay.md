# Each batch reports its mutation catch share and replays known defects

## The ruling

Owner, 2026-11-05 07:41 CST (waiting-page item 163, Cockpit item `mutation-ci-job`, pick d): "Report only, plus known-bug replay". Note with the pick: "we also reopen this in a while after logging for a bit".

The shared action `actions/mutation-report` runs on each batch's integration pull request and on workflow_dispatch. The scope step (`.github/scripts/ci-scope.sh`, output `mutation_report`) knows a batch by its head ref `batch-*`, the name every batch branch has used (batch-10, batch-11, batch-63e). No code fixes that name, so a batch branch named otherwise skips both steps and its job reads passed. Push and schedule runs skip both steps too. It has two steps:

- **Report.** `hooks/mutate_guard.py --changed` mutates only the product lines the batch added (merge base to head). Each mutated file runs every suite that the profile's `select` lists for it, changed or not. The step prints the catch share, which is the kill rate of decision `mutation-report-scores-suites` (killed over ran; a crash is not a kill). It prints one `untested: path:line` line per line whose mutant survived or reached no suite. A line whose mutants only crashed is in the share but not in the list. The budget is a wall deadline: a suite still running when it passes is killed, and its mutant counts as not run. The step exits 0 whatever the share. A low share never fails the job. A report that cannot run prints UNKNOWN and a warning, and exits 0: the report-only pick exempts it from decision `ci-unknown-is-red`.
- **Known-defect replay.** `hooks/mutate_guard.py --known-defects .github/known-defects.json --profile NAME` (or `--profile-file JSON`) re-plants each named past defect in a copy of the head tree and runs the suite named to catch it. The copy gets the profile's install, as `--changed` does, so a catcher that needs packages can run. CAUGHT needs an assertion red. A green run or a crash is MISS. A red clean run, a plant text that is missing or found more than once, or an install or link that fails, is UNKNOWN. A missing list file is UNKNOWN too. An empty list `[]` names no defect and passes, unless the base list names an entry. A MISS or an UNKNOWN fails the job. With `--base origin/<base>` the head list is also read against the base list. An id on the base list with no result row is `MISSING` and fails the job, unless a commit in the pull request carries the trailer `Known-defect-removed: <id>`. A trailer names one exact id per line. It sits in the message's last block, beside `Co-Authored-By`, because git reads trailers only there. An id on both lists whose entry differs is `CHANGED`. The entries are compared as parsed objects, so key order and spacing do not count. A `CHANGED` fails the job, unless a commit carries `Known-defect-changed: <id>`. The two trailers are not interchangeable. A base entry with no `id` is UNKNOWN. Those trailers are the visible removal and change steps. A base ref that does not resolve is UNKNOWN. A base with no list file passes.

The modes are part of the one home of mutation testing (`hooks/mutate_guard.py` with `hooks/mutate_shared.py`, decision `mutation-report-scores-suites`). `replay_pr` keeps its changed-suites-only default.

## Why a known-defect miss fails the job

A known-defect miss means that a test which once caught a real defect no longer catches it. The two named incidents were such losses: 3297d8fa (a lane deleted the test that pinned merge.py's ten-minute lock spare) and df25a68d (a fix deleted the tests that pinned its own two fixes). The suites that catch them are back on main, and the known-defect replay keeps them there. (The replay of merged pull requests in decision `mutation-report-scores-suites` is another mode.)

Evidence, 2026-11-05, main 0497265b, each plant applied by hand in a copy of the tree:

| Defect | Catcher | Clean runs | Planted runs | Gold |
|---|---|---|---|---|
| `df25a68d-rlock`: `_LIVE_LOCK` back to `threading.Lock()` | `hooks/test_mutate_replay.py RequestStopTests` | 3 green | 3 red, assertion | 3 red |
| `df25a68d-pw-timeout`: the timeout and closed-target test dropped from `classify_playwright` | `hooks/test_mutate_replay.py PlaywrightClassifyTests` | green | 3 red, assertion (87-90 s, whole file) | 3 red |
| `3297d8fa-take-spare`: `+ 10` dropped from the lock take call | `merge/test_merge.py LockProseStatesTheCode` | 1 green | 3 red, assertion | 3 red |

Every run was the same, and none needed the network. A fixture suite in `hooks/test_mutate_ci.py` proves that a catcher which pins nothing reads MISS. So a known-defect miss names a lost test, not a flake. An UNKNOWN is red under decision `ci-unknown-is-red`. A plant text that a refactor moved is re-pointed in `.github/known-defects.json`, red then green (`outcomes-tests-are-statements`), and the commit carries `Known-defect-changed: <id>`.

The silent-undo check (`lint/check_silent_undo.py`) does not see these losses. Its read of the two batches that landed them (PRs 1082 and 1075) flagged other files only. The waiting item `no-undo-net-loss-dial` holds the read that would.

## The log

Each run uploads one artifact, `mutation-report`, with two JSON files: the report (base, head, profile, made, killed, crashed, survived, not_run, untested) and the replay verdicts. The job summary shows the catch share and the untested lines. GitHub keeps artifacts 90 days by default.

Reader: the owner, when item 163 is reopened. The read is on demand: `gh run list --workflow checks.yml --branch <batch>` and then `gh run download <run> -n mutation-report`. Nothing commits a log to the repo.

## Cost

Measured locally, 2026-11-05, on batch 11 (59bff081 to 0497265b), 4 cores, with the job's settings: 10 mutants, a 300 s budget, a 180 s suite timeout. The range changed one product file, `hooks/stall_watch.py` (a fact of that batch, not pinned).

| Step | Wall time | Process starts | Files written | Target |
|---|---|---|---|---|
| `--changed` | 337 s; 326 s on a rerun | 75 direct (26 git, 49 suite or select runs) | 4 temp checkouts of 905 files and 49 run files, all removed; one JSON log | under the cap |
| `--known-defects` | 7 s, 3 of 3 CAUGHT, under a profile with no install; a profile with an install adds one install per lockfile hash, install and link, up to 900 s each | one checkout and 2 suite runs per defect, plus those installs | temp checkout and deps folder, removed; one JSON log | under the cap |

The job cap is 15 minutes (decision `ci-job-caps`). The first batch run (run 42064515414, 2026-11-05) took 34 s for the mutation-report job and 21 s for its step "Mutation report and known defects", on a sample of 9 mutants. The cap stays at 15 minutes, because a 9-mutant sample does not bound a full batch: the budget per change does. The cost per batch grows with the product lines the batch adds, up to the budget per change.

The share moves with the sample, the budget and the load of the machine. The same range read 4 of 10 killed (6 untested lines), then 1 of 5 with 5 not run on a loaded rerun (not pinned). Read a share as "a gap exists", not as an exact figure. The selector also reads each tracked `test_*.py` that imports or loads the file, parsed with `ast` (`hooks/test_mutate_ci.py` pins the forms), besides the `test_<stem>` files beside it. So the replay code in `hooks/mutate_shared.py` reads tested by `hooks/test_mutate_replay.py` and `hooks/test_mutate_ci.py`. Cost of `python3 hooks/mutate_guard.py --tests-for hooks/mutate_shared.py`, 3 runs each: 0.07 s before (0.065 to 0.100 s), 2.7 s after (2.71 to 2.78 s, remeasured once the selector followed names bound inside a function) (not pinned). It starts one process (one `git ls-files`), reads each tracked `test_*.py` (109 files, counted with `git ls-files | grep -cE '(^|/)test_[^/]*\.py$'`) and writes none (not pinned). A load through a function parameter is still missed (debt `tests-for-misses-param-loads`: the selector misses a load whose path is a parameter).

A test in `hooks/test_mutate_ci.py` proves that each mode writes only its `--log` file and leaves the repository as found.

## Adoption

claude-settings first. Each child repo adopts the action in its own lane. q_max and banchi have profiles and per-file selectors already. Each needs the action pin, a checkout with `fetch-depth: 0`, and a `.github/known-defects.json`. degen, mailaudit, home, ios-adblock and joyous also need a profile and a selector.

Kind: process
Home: hooks/mutate_shared.py
