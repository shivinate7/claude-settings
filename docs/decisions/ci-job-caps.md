# Each CI job's cap leaves its slowest run under 80%

## The ruling

Owner, 2026-11-01 18:44 CST: each owner repo raises its job caps generously, as a stopgap, until its time-pinned tests are gone. The owner named the CI fix step that ends the stopgap; it reads as decision `test-strategy-reset` (tests prove outcomes and never fail on runner speed). This repo's caps, with their measured runs, are in the table below.

Owner, 2026-10-27, roadmap step c95 (the cap rule):

- A full CI run is red only when something is broken, never because a job ran out of time.
- The target is a slowest run under 80% of the cap.
- A job that ends at its cap with no red test step is re-capped or split, never left (skill `ci-hygiene`, step 5).
- A cap rises only with a measured figure in the comment beside it. This item is suspended while the stopgap holds, and comes back when roadmap step `time-pinned-tests-go` (time-pinned tests are gone) closes (owner, 2026-11-01 18:44 CST, above).

## The table

Window: the newest 30 completed runs of each job in `checks.yml`, from run 39969158671 (2026-10-23) to run 40551443745 (2026-10-27). Main at the time was 9264397. Times are minutes from job start to job end.

| Job | Runner | n | Median | Slowest | Cap before | Cap after | Slowest as % of cap after | Cap ends, no red step | Target met |
|---|---|---|---|---|---|---|---|---|---|
| checks (window of 2026-11-05) | ubuntu | 27 | 19.8 | 22.8 | 52 | 52 | 44 | 0 | yes |
| checks-merge-install (split off checks; window of 2026-11-05) | ubuntu | 30 | 19.0 | 20.6 | none | 60 (provisional) | 34 | 0 | yes |
| checks-guard (window of 2026-11-05) | ubuntu | 31 | 16.4 | 18.5 | 22 | 22 | 84 | 0 | no |
| checks-windows-rest | windows | 30 | 17.0 | 43.0 | 38 | 28 | 48 (13.3 projected) | 1, against the cap in force (38) | yes after the split |
| checks-windows-sweep (new) | windows | 30 | 7.3 | 19.1 | none | 40 | 49 (19.6 projected) | 0 | yes |
| shell-macos (window of 2026-11-05) | macos | 24 | 20.9 | 23.2 | 28 | 28 | 83 | 0 | no |
| checks-macos (window of 2026-11-05) | macos | 30 | 19.4 | 30.5 | 55 | 55 | 55 | 0 | yes |
| checks-macos-b (split off checks-macos; window of 2026-11-05) | macos | 29 | 18.3 | 21.5 | none | 60 (provisional) | 36 | 0 | yes |
| checks-windows-guard (window of 2026-11-05) | windows | 32 | 8.4 | 19.7 | 20 | 20 | 99 | 0 | no |
| checks-windows-guard-2 (window of 2026-11-05) | windows | 14 | 17.0 | 19.9 | 20 | 20 | 99 | 0 | no |
| checks-windows-merge (window of 2026-11-05) | windows | 26 | 8.2 | 13.6 | 15 | 15 | 90 | 0 | no |
| checks-windows-merge-2 to -5 (window of 2026-11-05) | windows | 14 each | 10.6 to 13.4 | 12.2 to 14.0 | 15 | 15 | 82 to 94 | 0 | no |
| pointer-windows | windows | 30 | 3.8 | 4.2 | 10 | 10 | 42 | 0 | yes |
| checks-mutate-guard | ubuntu | 30 | 3.7 | 3.9 (old window; see the note below) | 10 | 25 | about 64 (16 projected for batch 7) | 1, run 41786084869, against the cap in force (10) | projected yes |
| checks-windows | windows | 30 | 1.2 | 1.6 | 10 | 10 | 16 | 0 | yes |
| checks-shoot | ubuntu | 30 | 0.8 | 1.0 | 10 | 10 | 10 | 0 | yes |
| scope, ci-done | ubuntu | 30, 19 | 0.1 | 0.1 | 5 | 5 | 3 | 0 | yes |

- Window of 2026-11-05: the rows marked so use the 99 newest completed runs of `checks.yml`, 2026-11-05 17:26 to 2026-11-06 18:00 UTC. 34 of them ran jobs, from run 42074654512 to run 42263498384; the rest skipped every job. The API listing stopped at one page, so runs from 2026-11-03 23:39 (the split) to 2026-11-05 17:26 are not in it. n counts green runs of the job, whatever the run's own end. No run was a re-run and none ended at a cap. Minutes come from `job_minutes` in `merge/merge.py`. Nine jobs are over the 80% target, all in this window; debt `jobs-over-80pct-of-cap` (jobs past 80% of their cap) holds them. Their caps are unchanged.
- `checks-mutate-guard` (lane mutate-guard-cap, 2026-11-04): run 41786084869 ended at the 10 min cap with 482 of 486 mutants printed KILLED and no red step. Two slow kills were sped up, with no kill lost. A local run with 4 jobs then took 651 s, against 710 s before. The cap-cut step ran 580 s or more. Batch 7's lanes add mutants. The coordinator measured, on main, lane PR 1163 alone at 946 s locally and lane PR 1157 at 768 s. The sum 710 + 236 + 58 - 59 is 945 s, about 16 min, if the added mutants add up and the speed-ups carry over. That is 64% of a 25 min cap if CI runs as fast as the local machine. A cap-cut step has no upper bound; the next green run on main replaces the projection. Debt `mutate-guard-split` holds the split.
- Every after-figure for a new or re-capped job (checks-guard, checks-windows-rest, checks-windows-sweep) is projected. The projection subtracts the measured step times of the moved suites from the measured job times. Cap ends count against the cap in force before this change.
- One full run on the branch (workflow dispatch, run 40559535659, 2026-10-27) measured each job under its new cap: checks 16.9 of 36, checks-guard 7.4 of 22, checks-windows-rest 6.2 of 28, checks-windows-sweep 12.4 of 40, shell-macos 7.6 of 18. The highest was checks-windows-guard-2 at 13.0 of 20 (65%). One run is n=1, so the next 30 runs on main replace the projections.
- `checks-windows-rest`: run 40542065223 (push to main) ended at the 38 min cap that was in force. The job started 16:33:37 UTC, so the cap fired at 17:11:37. GitHub's cancel grace then ran 5 more minutes, to 17:16:37, which is the 43.0 min figure. The step "Record stamp engine fixture suite" (normal slowest 1.5 min, n 28) started at 16:53:15 and never finished. That step now has its own 5 min cap, so a hang reads red at the step.
- `shell-macos`, the figures that set its 28 min cap (the row now holds the window of 2026-11-05): 18 runs of `checks.yml` from run 41355883918 (2026-11-01 22:11 UTC) to run 41407916830 (2026-11-02 07:41 UTC): 16 green runs and 2 cap ends, range 8.77 to about 19.2 min, median 12.27. Run 41407916830 (PR batch-63e) took 18.07 min in full, not a floor: the job started 07:41:39Z, the steps ran 07:41:40Z to 07:59:40Z, Complete job ended 07:59:42Z, and the cap cancelled the job at 07:59:44Z. Every step was green. Step times in min: checkout-detection 10.80, install_from_main 1.72, ios-ship 1.70 and 1.58, sim-test 1.02 and 1.00. Run 41407758669 (batch-63c, the ready run) is a floor: the job started 07:41:34Z, so the 18 min cap fired at 07:59:34Z, yet the steps ran on. Step times in min: checkout-detection 11.68 (07:41:45 to 07:53:26), install_from_main 1.73, ios-ship 1.70 and 1.85, sim-test (/bin/bash 3.2) 1.02. Then sim-test (bash on PATH) started 07:59:44Z and was cancelled at 08:00:46Z after 1.03 min, which is that step's normal length. The run took about 19.2 min. The sim-test steps grew from 0.05 and 0.03 min in run 41355883918 to about 1.0 min in the newest runs. Runs 41406600962 (batch-63c) and 41375543494 (batch-60), at 11.55 and 13.90 min, were cancelled by other acts, not by the cap, and are left out. The step "install.sh checkout-detection suite" grew (slowest 11.68 min; 10.80 in run 41407916830; mean 6.18 to 7.79 min, oldest against newest six green runs), so it has its own 16 min cap; its slowest is 73% of that cap.
- `checks-macos`, the figures that set its 55 min cap, before the split (the row now holds the window of 2026-11-05): 20 runs of `checks-macos` from run 41361394638 (2026-11-01 23:17 UTC) to run 41413936732 (2026-11-02 08:33 UTC): 15 green runs, range 25.6 to 37.1 min, median 31.1, no cap ends. The other 5 runs are left out: 3 were cancelled early by a newer run on the same branch (14.1, 21.6 and 11.5 min) and 2 failed (27.3 and 30.1 min). The slowest, run 41413936732 (PR #1075), is 74% of the old 50 min cap, so the 80% target was already met; the merge tool's 70% warning fired. The new 55 min cap is a stopgap under the owner's 2026-11-01 18:44 CST ruling above (37.1 is 67% of it). No step grew by more than 1 min. The step "Guard fixture suite" took 13.0 to 13.5 min on average, 16.62 min at most, 42% of job time, so it has its own 22 min cap (16.62 is 76% of it). The job is split since 2026-11-03: see the split bullet below. The `checks` figures come from the same 20 runs, 41361394638 to 41413936732 (2026-11-01 23:17 to 2026-11-02 08:33 UTC), job minutes. That window is newer than the window of the `checks` row in the table (2026-10-23 to 2026-10-27) and differs from the projected 19.8 min below. The split keeps the macOS jobs at 3 (with shell-macos): a fourth would queue, as checks-macos waited 379 s in run 41383013723.
- `checks-windows-sweep`: the fixture suite takes 8.2 min slowest and the mutation test 10.9 min slowest (push only).
- `checks`, the figures that set its 52 min cap, before the split (the row now holds the window of 2026-11-05): 20 runs of `checks.yml` from run 41361394638 (2026-11-01 23:17 UTC) to run 41413936732 (2026-11-02 08:33 UTC): 16 green runs, range 25.2 to 35.4 min, median 28.9, no cap ends. The other 4 runs are left out: 2 were cancelled by a newer run (13.0 and 11.5 min) and 2 failed (11.8 and 23.7 min). The slowest, run 41407916830, is 98% of the old 36 min cap. The new 52 min cap is a stopgap under the owner's 2026-11-01 18:44 CST ruling above (35.4 is 68% of it, under the merge tool's 70% warning). Step times in min, mean of the oldest 6 green runs to the newest 6, with the maximum: merge tool git-half fixture suite 6.20 to 6.43 (7.22); install.sh checkout-detection suite 3.67 to 5.83 (6.98); stall watch 2.89 (2.92). The checkout-detection suite is the only step that grew by more than 1 min, so it has its own 10 min cap (6.98 is 70% of it). In the newest 6 runs, hooks suites are 36.7% of job time, merge 24.4% and lint 16.6%, so no family dominates. The job is split since 2026-11-03: see the split bullet below.
- Split of 2026-11-03, for wall time. Run 41730427997 was a workflow dispatch on main with the full suite. checks-macos took 40.6 min: it started 8.8 min after the dispatch, in the macOS queue, and ended at +49.5 min. `checks` took 33.4 min. The next slowest job was checks-windows-guard at 19.1 min. The split moves CI steps whole, each with its own `if:`, shell, env and cap. Each suite still runs in one job per event. checks-macos runs the guard suite in 2 shards: `GUARD_SHARD` 1/2 here and 2/2 in the new job checks-macos-b. checks-macos-b also takes the stall watch (282 s), the janitor triggers (265 s) and 3 hooks suites (88 s). The janitor sweep suites stay in checks-macos. The new job checks-merge-install takes the merge suites (388 s), the install suites (492 s) and the janitor triggers (111 s) from `checks`. Medians after the split, in the window of 2026-11-05, on a push and on a pull request (n 13 each): checks-macos 20.5 and 18.7, checks-macos-b 18.0 and 18.3. Then `checks` 20.2 and 19.2, and checks-merge-install 19.3 and 17.9. checks-macos is faster on a pull request because the janitor sweep mutation test runs off pull_request only. Guard shard 1 took median 9.33 min, slowest 13.23; shard 2 median 9.10, slowest 11.20 (n 31 each). Against the medians before the split, checks-macos fell by about 702 s (31.1 to 19.4 min) and `checks` by about 546 s (28.9 to 19.8). The projections were 1180 s and 991 s; the cause of the gap is unmeasured. A whole green run, from its start to its last job's end, took median 22.6 min on a push and 22.7 on a pull request (n 13 each). Before the split the only figure is run 41730427997, n 1: its last macOS job ended 49.5 min after the dispatch. The slowest push run, 42080963752, took 86.8 min: its job checks-windows-rest was created about 70 min after the run, and the cause is unmeasured. A pull request with no macOS-scoped change starts the macOS jobs idle, every CI step skipped. Idle cost, 2026-10-24 to 2026-11-06 UTC (How to measure again, item 7): in this repo 101 idle macOS jobs, 115 billed min, 1.2% of 9931 macOS min on pull request runs. In all six repos with a macOS job, 284 idle jobs, 344 min. The public repos (claude-settings, mailaudit, banchi) pay nothing for hosted runners. The private repos (home, ios-adblock) idled 23 min, $1.43 at $0.062 a min before included minutes. An idle job holds a macOS slot for about 1 min; the queue wait it causes is unmeasured. So the idle runner is no real cost, and the jobs keep no job-level skip. Each new job keeps the 60 min provisional cap (How to measure again, item 6), now at 34% and 36%. So `merge.deadlineMinutes` in `.github/stamp.json` stays 65, the largest cap plus 5.

## How to measure again

1. List the newest 30 completed runs of `checks.yml` with `gh run list --workflow checks.yml --status completed`, and read each run's jobs with `gh run view <id> --json jobs`.
2. For each job, take minutes with `job_minutes` in `merge/merge.py` and the cap with `job_caps` in the same file. Do not write a second reader.
3. A cap end is a run whose job minutes reach the cap, whose conclusion is cancelled or failure, and with no failed test step.
4. Per-step times come from the GitHub API job steps (`started_at` and `completed_at`).
5. A run cancelled before its cap by another act, such as a newer push or a batch rebuild, is left out of the sample, and the record names it.
6. A new job takes a provisional cap of 60 min until it has 5 green runs. Keep `merge.deadlineMinutes` in `.github/stamp.json` at least the largest cap plus 5.
7. Idle macOS minutes on pull requests: save the script below as `measure.py` and run `python3 -I measure.py 2026-10-24 2026-11-07 shivinate7 claude-settings banchi degen home ios-adblock mailaudit` (the end date is exclusive). Per repo it prints pull request runs, macOS minutes, idle macOS jobs and minutes, and the runs whose diff changes only `*.md` files or files under `docs/`. Here `*.md` holds rules and skills, so most such runs are not idle: 17 runs, 198 min, of which 25 idle. Cost: per run of the script, one runs read per repo-day, one jobs read per run, and up to three reads per pull request head; run on demand.

```python
# Usage: python3 -I measure.py <since YYYY-MM-DD> <until YYYY-MM-DD, exclusive> <owner> repo...
# Sums macOS job minutes (each job rounded up to a whole minute, as GitHub bills) on pull_request runs,
# and the part spent on runs whose PR diff changes only *.md files or files under docs/.
import json, math, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta
def get(path):
    for i in range(4):
        p = subprocess.run(["gh", "api", path], capture_output=True, text=True)
        if p.returncode == 0: return json.loads(p.stdout)
        time.sleep(2 ** i)
    raise RuntimeError(f"{path}: {p.stderr.strip()}")
def pages(path, key):  # pages by hand: the session proxy refuses the repositories/{id} links gh --paginate follows
    out, n = [], 1
    while True:
        items = get(f"{path}&per_page=100&page={n}")[key]
        out += items
        if len(items) < 100: return out
        n += 1
def t(s): return datetime.fromisoformat(s.replace("Z", "+00:00"))
def docs_only(files): return bool(files) and all(f.endswith(".md") or f.startswith("docs/") for f in files)
since, until, owner, repos = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
for repo in repos:
    r = f"repos/{owner}/{repo}"
    d0, d1, runs = date.fromisoformat(since), date.fromisoformat(until), []
    while d0 < d1:  # one day per query: a filtered runs query returns at most 1000 results
        runs += pages(f"{r}/actions/runs?event=pull_request&created={d0}", "workflow_runs")
        d0 += timedelta(days=1)
    runs = [x for x in runs if x["conclusion"] != "skipped"]
    done = [0]
    def mac_minutes(run):
        done[0] += 1
        if done[0] % 50 == 0: print(f"  {repo}: {done[0]}/{len(runs)} runs read", file=sys.stderr, flush=True)
        jobs = pages(f"{r}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?filter=latest", "jobs")
        mac = [j for j in jobs if any("macos" in l for l in j["labels"]) and j["started_at"] and j["completed_at"]]
        bill = lambda j: math.ceil(max((t(j["completed_at"]) - t(j["started_at"])).total_seconds(), 1) / 60)
        # idle: every step but the runner's own setup, teardown and post steps was skipped
        idle = [j for j in mac if all(st["conclusion"] == "skipped" for st in j["steps"]
                                      if st["name"] not in ("Set up job", "Complete job") and not st["name"].startswith("Post "))]
        return sum(map(bill, mac)), len(idle), sum(map(bill, idle))
    def files(sha, branch):  # the PR that holds this head, compared from its base; a closed PR's run lists no PR
        prs = get(f"{r}/commits/{sha}/pulls") or get(f"{r}/pulls?state=all&head={owner}:{branch}")
        if not prs: return None
        return [f["filename"] for f in get(f"{r}/compare/{prs[0]['base']['sha']}...{sha}").get("files", [])]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(mac_minutes, runs))
        mins, idle_n, idle_m = [x[0] for x in res], sum(x[1] for x in res), sum(x[2] for x in res)
        heads = sorted({(run["head_sha"], run["head_branch"]) for run, m in zip(runs, mins) if m})
        fmap = dict(zip([h[0] for h in heads], ex.map(lambda h: files(*h), heads)))
    all_m = sum(mins)
    doc = [(run, x) for run, x in zip(runs, res) if x[0] and docs_only(fmap[run["head_sha"]] or [])]
    doc_m, doc_idle_m = sum(x[0] for _, x in doc), sum(x[2] for _, x in doc)
    unknown = sum(1 for run, m in zip(runs, mins) if m and fmap[run["head_sha"]] is None)
    share = f"{100 * doc_m / all_m:.1f}%" if all_m else "n/a"
    print(f"{repo}: pr_runs={len(runs)} runs_with_macos={sum(1 for m in mins if m)} docs_only_runs={len(doc)} "
          f"docs_only_macos_min={doc_m} all_pr_macos_min={all_m} share={share} no_pr_found={unknown} "
          f"idle_macos_jobs={idle_n} idle_macos_min={idle_m} docs_only_idle_macos_min={doc_idle_m}", flush=True)
```

Kind: process
Home: .github/workflows/checks.yml
