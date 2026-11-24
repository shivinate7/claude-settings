# Lane lint gets the 600 s hang stop, unmeasured on a Mac

**What.** Lane lint gives each suite the 600 s hang default through `bin/ci-job`, and no `--lint-unknown-ok` reason lifts a hang. A stop needs no new output and no CPU advance under the step for 600 s. `merge/test_lane_lint.py` ran 704.7 s with 27 log lines before its last line, and `hooks/test_stall_watch.py` showed a 519 s quiet gap in CI (one sample). Unmeasured: whether either suite can read as a hang on a Mac, where the CPU read is the subject of debt `hang-macos-false-hang` (a healthy macOS step read as a HANG). Claude meets it on a lane lint on a Mac that runs either suite.

**Where.** `bin/ci-job` `hang_default` (about line 890), which gives the default. `hooks/_nowindow.py` `HANG_SECONDS_DEFAULT` (line 34). The wait loop of `bin/verdict`. Two code caps the record does not yet rule as hang stop or net: the merge tool's `LINT_SECONDS` (3600 s, `merge/merge.py` about line 2572), and the mutation-run timeouts (`--suite-timeout` and `--budget` in `hooks/mutate_guard.py`).

**Decision.** `hang-stop` (a CI or lane lint step stops only on a hang).

**Retire.** None yet. Close when a lane lint run on a Mac that runs `merge/test_lane_lint.py` and `hooks/test_stall_watch.py` reads no HANG line, and decision `hang-stop` rules each code cap in Where as a hang stop or a net.
