# The guard mutation job grows with each batch and runs in one job

- **What.** `checks-mutate-guard` runs every guard mutant in one job, 4 at a time. Its step took 193 s, then 400 s in batch 4, then hit the 10 min cap in batch 5 (run 41786084869) at 580 s or more. Batch 7's lanes add more: on main, lane PR 1163 alone ran 946 s locally and lane PR 1157 768 s (coordinator's measure). Its cap is 75 min, an interim stopgap (owner 12:11 CST Nov 10). Each mutant starts a fresh suite run, so the job nears its cap again as the guard gains mutants.
- **Where.** Job `checks-mutate-guard` in `.github/workflows/checks.yml`, and `run_mutants` in `hooks/mutate_shared.py`.
- **Decision.** `ci-job-caps` (each CI job's cap leaves its slowest run under 80%).
- **Retire.** Split the mutants into shards across parallel jobs, with a check that each mutant runs in exactly one shard, as `lint/test_windows_split.py` checks for the suites. The check is each shard's step time from one CI run.
- **Status.** Shards built (lane mutate-guard-split). Retire this record once one PR run shows each shard's step time under 25 min.
