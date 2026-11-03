# verdict reads PASS on rewritten xcodebuild output with no test count

**What.** `verdict` fails a test run that reads no test count only when it sees a test run: an xcodebuild test success marker at a line start, or `xcodebuild test` or `swift test` as typed. A run wrapped in a shell with its output rewritten, such as `verdict sh -c "xcodebuild test | xcbeautify"`, shows neither. A no-count run then reads PASS. An iOS repo may pipe xcodebuild through a formatter in normal work.

**Where.** `bin/verdict`, `TEST_OK` and `test_argv`.

**Decision.** Rule `verification-report-unknown-reads` (a read that could not run is unknown, never clear).

**Retire.** Read the formatter's own summary as a count and its success line as a marker, from a real xcbeautify log (unmeasured: which lines xcbeautify keeps). Closed when a red case with that log and no count reads FAIL, and the same log with a count reads PASS.
