# The pick check reads a word list, and its hit rate is unmeasured

- **What.** The check on a coordinator's `send_message` decides "this states a pick" from a word list. It refuses non-statements ("I'll pick a port", a code span, `held` in a brief) until the sender adds `no ruling found:`. It passes other wordings ("going with", "Decision:", "my call is"). Round 3 of its review (2026-11-12) found a coordinator is likely to hit this in normal work.
- **Where.** `hooks/call_judge.py`, `PICK_WORD`.
- **Decision.** `pick-cites-ruling-before-send` (a pick cites a ruling before it is sent).
- **Retire.** Read the `pick-judge` lines in guard.log after a week of coordinator use, count the false alarms and the missed picks, and re-cut the word list or drop the check. A case in `hooks/test_call_judge.py` keeps each counted false alarm passing.
