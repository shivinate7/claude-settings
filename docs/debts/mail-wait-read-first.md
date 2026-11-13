# Mail wait misses mail open at a restart

**What.** `mail wait` takes its baseline of open ids at each start, so mail open at a start never wakes it. Mail that lands mid-turn, after the turn-start read, goes unseen. A poll with two or more new messages names only the first, and the restart then hides the rest. The skill never says to run `mail read` before each start.

**Where.** `hooks/mail.py` `wait` (baseline and `fresh[0]`), the doorbell bullets in `skills/waiting-page/reference/routing-and-sessions.md`, and the "The doorbell: mail wait" section of the decision.

**Decision.** `session-messages`, the git mailbox. Its doorbell section names the baseline rule.

**Retire.** Add the line "run `mail read` before each start" to the skill and the decision section, and add a case for two new messages in one poll. Shown closed by `hooks/test_mail_wait.py`.

Found in PR 2990 review round 3 (reviewer sonnet). Likelihood: normal work hits it when mail lands during a long turn.
