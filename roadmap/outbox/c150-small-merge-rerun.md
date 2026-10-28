# c150-small-merge-rerun

- c150 status: try 1 pushed at 74428e57 (branch c150-small-merge-rerun). Review round 1 (Opus) found one blocking hole: `DOC_SUITES`, a hand list of suites that read docs, misses hooks/test_sendmessage_state.py and skills/project-ops/tests/test_scaffold.py. Try 2 (builder, Opus) derives that set from gates.yml. Resume: read the branch log, then send a fresh reviewer the round-1 findings.
- Finding, no step yet: hooks/test_guard.py case "load-brake: probe control: a child process the probe starts is counted" fails (counted 2, want 1) on main e0f9e2d in a cloud container. It is not caused by c150. Unknown whether CI hits it.
