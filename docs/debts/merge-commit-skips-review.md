# A merge commit can skip review

**What.** While it resolved a merge of main into a lane branch, a builder pushed a logic change to `lint/report_guard.py`. The change made the Stop path read the reply once instead of three times. No reviewer read it. Lane lint passed. The gap was found only because the batch runner asked. The harm: an unreviewed change to a guard verdict path could reach main. Claude is likely to repeat it, since conflict fixes during restacks are common.

**Where.** `lint/report_guard.py` (the guard file changed), lane lint, and the batch runner's intake.

**Decision.** `none`. The rule that makes this a debt is `building-mistake-names-its-guard` (a mistake names the guard that would have stopped it).

**Retire.** Make lane lint, or the batch runner's intake, refuse a non-merge commit that comes after the last review and touches a guard or check path. A review record must name that commit to let it through. Check: a fixture with such a commit. The check refuses it. Red on the current code, green after the fix.
