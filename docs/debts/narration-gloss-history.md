# narration-gloss-history

**What.** Round narration passes the comment-narration check when it sits inside a decision gloss whose id holds the same `round-N`, as in "(decision hold-unsafe-after-round-3, fixed in review round 3)" and "(see decision hold-unsafe-after-round-3, added after round 3)". No word window tells such history apart from a quote of the rule.

**Where.** `lint/check_comment_narration.py`, class ReviewRound. The same pass runs in every pinning repo, through actions/code-check, for a claude-settings decision id.

**Decision.** `none`.

**Retire.** Fix: `step:clause-parser-claims` reads the clause inside the gloss and flags a history verb next to the round. A FLAGGED case for each example above goes green in `lint/test_check_comment_narration.py`.

## Ruling

The coordinator ruled this a debt, not a note (2026-11-08 05:17 CST). Its fix waits on `step:clause-parser-claims`, the gloss-clause parser.
