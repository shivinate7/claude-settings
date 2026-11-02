# A reply never says a record was rewritten for a ruling it predates

## The ruling

The report guard (`lint/report_guard.py`) checks each landed turn's reply. A sentence may say a decision was rewritten (rewritten, rewrote, rewrites, rewrite of) for a ruling. It blocks when that decision's record was last committed before the ruling. Both the default branch and HEAD must predate it. The record then has not moved, so the sentence is false.

Named incident F119, landed 2026-11-01. Sessions said decision `ci-job-caps` was rewritten for the owner's 2026-11-01 18:44 CST ruling. Main showed the record last touched on Oct 28.

- A cited id is a word in the sentence that names a file in the decisions folder of the checkout. The folder comes from `layout`. No "decision" word is needed. An id that follows "under" or "by" names the ruling, not a rewrite, and is skipped.
- A rewrite word that a negation or a future tense just before it undoes claims nothing. "Not rewritten yet", "was never rewritten" and "will be rewritten" pass.
- The ruling time is the stamp tied to the word "ruling". The stamp is `YYYY-MM-DD HH:MM <zone>`, or `HH:MM <zone>` on the turn's Central date (the last human record's timestamp, Central, through `hooks/local_time.py`). It follows the word within 30 characters, or sits right before it. Another stamp in the sentence, such as a merge time, is not the ruling time. Zones read: CST, CDT, UTC, GMT.
- A sentence with no stamp tied to "ruling" passes. A later commit on the ruling's own record is no fallback, because a typo fix there would cry wolf. "In place" alone does not trigger.
- Every cited id in the sentence is checked. The block names only the stale ones, with the last commit date in Central 24-hour time, the ruling time and the remedy: rewrite the record first, or say it is not rewritten yet.
- Fails open: no record file, no time, no default-branch ref, git missing or failing. Each passes.
- Shallow-clone limit: a shallow clone cuts history, so the record's last commit can read later than it is. The check then misses a stale rewrite. It never blocks a fresh one.

Cost: one regex read of the reply. Only on a reply that matches it: file reads (the decisions folder, and the git folder's refs for `main`, `master` and their `origin/` forms), and one `git log -1` per cited id with a record file, at most 5. A reply that cites no id with a record file runs no git. No file is written, and no timer or log is kept. `RewriteStampTests` in `lint/test_report_guard.py` proves the git count with `GIT_TRACE`.

Kind: process
Home: lint/report_guard.py
