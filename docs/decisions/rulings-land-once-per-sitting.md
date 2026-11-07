# Several rulings on one question in one sitting land as one rewrite

## The ruling

Owner, 2026-11-02 10:41 CST, ruling fb-1041-2 ("Stop rule churn and drift in the other repos"):

- When the owner gives two or more rulings on the same question in one sitting, the session holds them for 30 minutes after the last one. Then it lands one rewrite of that question's record, in one PR. It does not open one PR for each message.
- While it holds them, each ruling is a scratch note in the session's report (`output-answer-has-a-home`, an answer is a ruling), with the owner's words and time.
- The rewrite keeps the time of each ruling, so the hold loses nothing.
- Exception: a ruling that unblocks a running lane lands at once. The rest of the sitting still lands as one rewrite.

Incident: on 2026-11-01, from 19:19 to 21:34 CST, the merge grant was rewritten three times. In one hour, idle compaction was turned off, turned back on and turned off again. Each step was its own PR, and child repos copied a step that was soon out of date.

## Not mechanized

No check counts the 30 minutes. At each wake, the session reads the time of the owner's last ruling on the question. No timer counts (`questions-go-to-owner`, questions go to the owner).

Kind: process
Home: docs/decisions/rulings-land-once-per-sitting.md
