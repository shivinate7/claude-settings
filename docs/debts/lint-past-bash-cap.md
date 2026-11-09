# Cloud lint runs past the 600 s Bash cap

- **What.** Cloud `./bin/verdict ./bin/ci-job checks --lint` took 630-649 s over 2 runs on 2026-11-07 (514-547 s over 4 runs on 2026-11-06). One Bash tool call stops at 600 s, so a foreground run moves to the background with no verdict, and `merge --lane-lint` runs under the same cap. On Windows the run took 840 s.
- **Where.** `bin/ci-job` `--lint`: it runs each fixture suite one after another, and fixture suites take most of the time (Compliance probes 64 s, Stop-hook guard 53 s on cloud).
- **Decision.** `ci-job-caps` (each CI job's cap leaves its slowest run under 80%).
- **Retire.** The lint runs under 480 s on cloud, for example by running steps in parallel or by leaving fixture suites to CI, and a test pins the cost: `lint/test_ci_job.py`.
