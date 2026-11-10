# lane: judge-replay-corpus (session_013NEJL3zaJYqXCK4XMrELwY), received 11:07 CST 2026-11-10, kind B

(B) Handoff, lane judge-replay-corpus (resent; first sent 2026-11-10 10:04 CST):
1. Work: a replay corpus per model judge (11 judges, 58 cases), CI job judge-replay with a sign-in probe (item 283 closed green), and a feedback_guard retry for items with no verdict (owner item 279 pick b).
2. shivinate7/claude-settings, branch judge-replay-corpus, PR 1327 (draft), head 3aa89b15e. All pushed; nothing local.
3. State: both parts passed review round 2 (sonnet), and the local fix checks are green. Handed for batch runner 8 on 2026-11-06 14:43 CST, never batched. No CI run has tested this head, and main has moved since.
4. Left: merge main in, then batch it. The judge-replay job makes about 59 model calls when a batch touches a judge scope.
5. Notes sit in docs/debts/notes.md on the branch.
