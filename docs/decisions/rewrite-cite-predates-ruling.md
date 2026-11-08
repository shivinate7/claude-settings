# A reply never says a record was rewritten for a ruling it predates

## The ruling

The report guard (`lint/report_guard.py`) checks each landed turn's reply. A sentence may say a decision was rewritten (rewritten, rewrote, rewrites, rewrite of) for a ruling. The guard refuses it when that decision's record was last committed before the ruling. The record then has not moved, so the sentence is false.

Named incident F119, landed 2026-11-01. Sessions said decision `ci-job-caps` was rewritten for the owner's 2026-11-01 18:44 CST ruling. Main showed the record last touched on Oct 28.

- A cited id is a word next to the rewrite word that names a file in the decisions folder of the checkout. The folder comes from `layout`. No "decision" word is needed.
- Next to the rewrite word means right before it ("decisions X and Y were rewritten") or right after it ("rewrote decision X"). An id after under, by, per, following or see is not checked.
- A queued sentence claims no rewrite. "Pending" or "queued" anywhere in the sentence skips it.
- A negation or a modal just before the rewrite word claims no rewrite. The words: not, no, never, yet, will, would, shall, should, must, can, may, could, need, needs, "to be" and "going to".
- The ruling time is the stamp next to the word "ruling": "the <stamp> ruling", "ruling at <stamp>" or "ruling of <stamp>". Another stamp in the sentence, such as a merge time, is not the ruling time.
- The stamp is `YYYY-MM-DD HH:MM <zone>`, or `HH:MM <zone>` on the turn's Central date. Zones read: CST, CDT, UTC, GMT.
- The turn's time is the last human record's timestamp, else the hook's clock (`hooks/local_time.py`). A clock-only stamp later than the turn's time names the day before.
- A sentence with no stamp next to "ruling" passes. A later commit on the ruling's own record is no fallback, because a typo fix there would cry wolf. "In place" alone does not trigger.
- The last commit is the newest one that touches the record on any local branch, any remote branch or HEAD. A rewrite pushed to any branch counts. The check does not read the default branch, so `default-branch-read-order` (how hooks find the default branch) keeps one reader.
- The refusal names only the stale ids, with the last commit date in Central 24-hour time and the ruling time. Its remedy: rewrite the record, fetch the branch that holds the rewrite, or say it is not rewritten yet.
- Fails open: no record file, no ruling stamp, git missing or failing. Each passes.
- Shallow-clone limit: a shallow clone cuts history, so the record's last commit can read later than it is. The check then misses a stale rewrite. It never refuses a fresh one.

Cost: one regex read of the reply (unmeasured). Only on a reply that matches it: a file check per cited id, and one `git log -1 --branches --remotes HEAD` per distinct id with a record file, at most 5 per reply. The same id in many sentences runs one git process (unmeasured). A reply that cites no id with a record file runs no git. No file is written, and no timer or log is kept. `RewriteStampTests` in `lint/test_report_guard.py` proves the git count with `GIT_TRACE`.

Kind: process
Home: lint/report_guard.py
