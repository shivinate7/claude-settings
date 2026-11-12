# A ruling claim restated in a Drops-lines trailer is flagged

**What.** A `Drops-lines:` trailer line (lines dropped on purpose) that restates a ruling claim is checked on its own. The line needs its own home and time, even when the body already cites the ruling. Seen on commit 9a5d06c8 (a commit that declares a reworded refusal line as a trailer). In the history checked, 1 honest cite was refused, out of 33 flags in 10,277 commits.

**Where.** `lint/check_red_run.py`, `missing_cite`: the last paragraph is checked alone, unless a `Ruling:` line in it names a home and a time.

**Decision.** `outcomes-grant-covers-named-act` (a grant covers the act it names, never a variant).

**Retire.** A claim restated in a `Drops-lines:` trailer passes when the body cites it. Cases in `lint/test_check_red_run.py` show it.
