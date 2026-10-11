# verdict reads a test runner's own failure markers

## The question

When does `bin/verdict` print FAIL for a command that exits 0?

## The ruling

Owner, 2026-10-11 ("start the verdict lane"):

1. A run whose output holds `** TEST FAILED **` or `** BUILD FAILED **` prints FAIL, also when
   the command exits 0. xcodebuild prints these exact markers only on a real failure, so they
   cannot raise a false alarm. verdict reads the whole output of the run, not only its tail.
2. A run whose output holds `Executed 0 tests` and no `Executed <n> tests` line with n above 0
   prints FAIL with the note `no tests ran`. A test command that ran nothing proves nothing. One
   empty bundle beside a bundle that ran tests passes.
3. verdict reads only these markers. It does not let its broad excerpt pattern (`FAIL`,
   `Error`, `assert`) change a verdict, because that pattern matches text in passing runs.
4. The exit code stays the command's own, except that a marker FAIL exits 1.
5. When verdict cannot read the run's log, it prints FAIL with the note `log unreadable`. A read
   that could not run is unknown, never a pass.

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
- verdict reads markers from its log file, which the child can reach. A child that truncates
  the log and then writes more can hide a marker. No test runner does this. A read from a pipe
  that verdict owns is the upgrade.
