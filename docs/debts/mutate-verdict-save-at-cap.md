# Mutation verdict save at a job cap is unprobed

- **What.** Each mutation shard job saves its verdicts in a save step that runs under `always()`. GitHub's docs do not say whether that step runs after GitHub cancels a job at its cap. No run has probed it. If it does not run, a rerun of a job cut at its cap restores nothing and judges every mutant again.
- **Where.** `.github/workflows/checks.yml`, the "Save the mutation verdicts" step of `checks-mutate-guard`, `checks-mutate-guard-b` and `checks-mutate-guard-c`.
- **Decision.** `hang-stop` (the hang stop; its resume list names the mutation verdict cache).
- **Retire.** A throwaway branch run with a 1-minute job cap on one mutation job. Check the cache list for the job's key after the cut. An entry means the save runs at a cap. Then rewrite the resume line in `hang-stop` in place.
- **Reported.** 2026-11-24 16:23 CST (lane `mutate-verdicts-cached-ci`).
