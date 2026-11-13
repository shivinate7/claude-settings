# The pick check reads word lists, and its hit rate is unmeasured

- **What.** The pick check decides "this states a pick" from a word list on `send_message`. On `create_session` (the lane brief) and `SendMessage` (an agent message) it reads statement markers. The `send_message` list refuses non-statements ("I'll pick a port", a code span) until the sender adds `no ruling found:`, or rewords. The brief tools pass a pick with no marker ("I pick route B") and a bare hold. The lane brief template (`skills/project-ops/templates/brief.md`) costs no judge call. Round 3 of its review (2026-11-12) found a coordinator is likely to hit this in normal work.
- **Where.** `hooks/call_judge.py`, `PICK_WORD` (`send_message`) and `PICK_BRIEF_MARKER` (`create_session`, `SendMessage`).
- **Decision.** `pick-cites-ruling-before-send` (a pick cites a ruling before it is sent).
- **Retire.** Read the `pick-judge` lines in guard.log after a week of coordinator use, on all three tools. Count the false alarms and the missed picks per tool. Then re-cut the word list and the markers, or drop the check. A case in `hooks/test_call_judge.py` keeps each counted false alarm passing.
