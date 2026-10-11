# verdict reads a test runner's own failure markers

## The question

When does `bin/verdict` print FAIL for a command that exits 0?

## The ruling

Owner, 2026-10-11 ("start the verdict lane"):

1. A run whose output holds `** TEST FAILED **` or `** BUILD FAILED **` prints FAIL, also when
   the command exits 0. xcodebuild prints these exact markers only on a real failure, so they
   cannot raise a false alarm.
2. An xcodebuild test run whose output holds `Executed 0 tests` prints FAIL with the note `no
   tests ran`. A test command that ran nothing proves nothing.
3. verdict reads only these markers. It does not let its broad excerpt pattern (`FAIL`,
   `Error`, `assert`) change a verdict, because that pattern matches text in passing runs.
4. The exit code stays the command's own, except that a marker FAIL exits 1.

## The incident

2026-10-11, shivinate7/home-app: `verdict xcodebuild test …` printed PASS. The log held
`** TEST FAILED **`, because the iOS test host was killed at bootstrap. verdict decides from the
exit code alone, so xcodebuild exited 0 for that run. The exit code is unmeasured: the run's
log is gone. In a second run, an `-only-testing` filter that matched nothing gave `Executed 0
tests`, `** TEST SUCCEEDED **`, and PASS.

## Named limits

- Other test runners' zero-test output is not read. pytest already exits 5 when it collects no
  tests.
- `verdict cmd | tail -3` drops verdict's own PASS or FAIL line. The fix is the caller's: do not
  pipe verdict.
