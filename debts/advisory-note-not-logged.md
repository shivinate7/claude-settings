# The advisory note leaves no log line

- **What.** The gate and the sweep show an advisory finding as a note and write no guard.log line for it. A write with advisory findings only leaves no trace. The 30-day trigger of deferred item `ste-into-agent-briefs` has no log to read.
- **Where.** The advisory branch of `main()` in `lint/ste_gate.py` and in `lint/md_sweep.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** Each advisory note writes one guard.log line through `guard_logger`, with the codes. A test pins the line. Or the decision records the missing log as accepted.
