# Cloud lint runs past the 600 s Bash cap

- **What.** Cloud `./bin/verdict ./bin/ci-job checks --lint` took 630-649 s over 2 runs on 2026-11-07 (514-547 s over 4 runs on 2026-11-06). One Bash tool call stops at 600 s, so a foreground run moves to the background with no verdict, and `merge --lane-lint` runs under the same cap. On Windows the run took 840 s.
- **Where.** `bin/ci-job` `--lint`: it runs each fixture suite one after another, and fixture suites take most of the time (Compliance probes 64 s, Stop-hook guard 53 s on cloud).
- **Decision.** `lanes-run-no-full-ci-job` (a lane runs `merge --lane-lint`, the one full `--lint` run, before it hands off). No decision covers the Bash tool cap itself.
- **Retire.** Retire this debt when, on cloud, `merge --lane-lint` gives its verdict inside one Bash call in 3 measured runs. Ways: run steps in parallel, or leave fixture suites to CI. No test times the run (decision `test-strategy-reset`, no test times a local run).
