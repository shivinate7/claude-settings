# The guard mutation job grows with each batch and runs in one job

- **What.** `checks-mutate-guard` runs every guard mutant in one job, 4 at a time. Its step took 193 s, then 400 s in batch 4, then hit the 10 min cap in batch 5 (run 41786084869) at 580 s or more. Batch 7's lanes add more: #1163 alone ran 946 s locally. Its cap is now 25 min. Each mutant starts a fresh suite run, so the job nears its cap again as the guard gains mutants.
- **Where.** Job `checks-mutate-guard` in `.github/workflows/checks.yml`, and `run_mutants` in `hooks/mutate_shared.py`.
- **Decision.** `ci-job-caps` (each CI job's cap leaves its slowest run under 80%).
- **Retire.** Split the mutants into shards across parallel jobs, with a check that each mutant runs in exactly one shard, as `lint/test_windows_split.py` checks for the suites. The check is each shard's step time from one CI run.
