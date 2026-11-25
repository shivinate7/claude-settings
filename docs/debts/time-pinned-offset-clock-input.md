# An injected clock with an offset is an elapsed-assert, and the keep marker cannot waive it

- **What.** `self.assertIsNone(f(1, time.monotonic() - 1))` reads a clock difference inside an assert call's arguments, so the finder lists it as an elapsed-assert. The test sets an injected clock, not a speed. The keep marker `time-pinned-ok` does not waive an elapsed-assert, so the line cannot be kept. `--check --base` now gates new lines, so a correct new line fails the check with no waiver. This was an old note that called the pattern "rare and harmless"; that no longer holds.
- **Where.** `lint/find_time_pinned.py`: `scan_file`, where `held` keeps every category except `elapsed-assert`; the `REMEDY` entry for elapsed-assert, which says the marker does not keep it; and `scan_python`, which reads a `-` inside a call's arguments as a measured duration.
- **Decision.** `test-strategy-reset` (point 2: a timed test uses a synthetic clock, as test-practices P5 says).
- **Retire.** `lint/test_find_time_pinned.py` has a case where an injected clock with an offset inside an `assertIsNone` call, with a keep marker, passes `--check --base`.
