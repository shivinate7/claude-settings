# The alarm's revert search can fail for good and hide a red main

- **What.** `actions/ci-alarm` reads reverts with one `search/commits` call per red run head, and one more per chain link. If that call fails for good under the Actions `GITHUB_TOKEN` (403 or 422), the alarm ends as `unknown` (a `::warning::`, no issue) for every red run that no clearing run covers. Without the revert read, those runs alarm. So a red main raises no alarm. Unmeasured under the Actions token. A user token got 200 on this repo (50 hits, 2026-11-13 15:49 CST). Found in PR #3273 (branch `ci-alarm-reads-reverts`) review, 2026-11-13.
- **Where.** `actions/ci-alarm/alarm.sh`, function `reverted`: exit 2 from `revert_rule.py` ends the run as `unknown`. `actions/ci-alarm/revert_rule.py`, function `revert_hits`: the search read.
- **Decision.** `no-merge-onto-red-main` (no batch merges onto a red main).
- **Retire.** Read one alarm run's log under the Actions token. If the search answers, close with a `Retire-run` cite. If it fails for every red run, consider an alarm-visible note for a failed revert read, pinned by `actions/ci-alarm/test_revert_read_alarm.sh` (not yet written).
