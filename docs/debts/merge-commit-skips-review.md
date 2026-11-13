# A merge commit can skip review

**What.** While it resolved a merge of main into a lane branch, a builder pushed a logic change to `lint/report_guard.py`. The change made the Stop path read the reply once instead of three times. No reviewer read it. Lane lint passed. The gap was found only because the batch runner asked. The harm: an unreviewed change to a guard verdict path could reach main. Claude is likely to repeat it, since conflict fixes during restacks are common.

**Where.** `lint/report_guard.py` (the guard file changed), `merge/merge.py` (`lane_lint`, and `batch_build_run`, the batch runner's intake).

**Decision.** `none`. The rule that makes this a debt is `building-mistake-names-its-guard` (a mistake names the guard that would have stopped it).

**Retire.** Make lane lint (`lane_lint`) or batch intake (`batch_build_run`) refuse a head. The refusal applies when its latest non-merge commit on a guard or check path comes after the reviewed head named in its review log. Today lane lint reads no review log, and batch intake reads none either. The `--batch-build` wrapper reads them only to print left-out lines. Only `--release-check` fails a stale review log, and its help says it runs before a batch runner gets a pull request. Check: `merge/test_lane_lint.py` gets a fixture for a pull request number whose review log names an earlier head, with a later non-merge commit on a guard path. Lane lint on that number must refuse it. The fixture is red on today's code and green after the fix. If step #3049, per-lane merge, removes batch intake, rewrite this Retire against the path that remains.
