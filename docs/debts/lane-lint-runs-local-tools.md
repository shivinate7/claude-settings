# Lane lint runs the local claude-settings tools

- **What.** `merge --lane-lint` runs `ci-job checks --lint`, which still runs remote code-check, zizmor and ste-lint, and steps that read `CLAUDE_SETTINGS_DIR`, from the local claude-settings checkout, not the commit the job pins. Pin lag is routine, so a lane lint can pass or fail where CI would not. The ready checks (`--step`) follow the pin since step `ready-checks-use-pinned-tools`.
- **Where.** `bin/ci-job` `--lint` mode; `merge/merge.py` lane_lint.
- **Decision.** `lanes-run-no-full-ci-job` (the lane-check decision).
- **Retire.** `--lint` follows the job's pin as `--step` does, and a case in `lint/test_ci_job.py` shows a lint step reading the pinned tree.
