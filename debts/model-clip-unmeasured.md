# Judge prompt clips are unmeasured

- **What.** The prompt now goes to `claude -p` on stdin, so no argv cap bounds it. `PROMPT_MAX_LEN` (20000) and `REPLY_MAX` (12000) now bound cost and latency only, and nobody has measured either.
- **Where.** `hooks/decision_watch.py` (`PROMPT_MAX_LEN`), `hooks/reply_judge.py` (`REPLY_MAX`).
- **Decision.** none
- **Retire.** Measure cost and latency of a judge call at 20k, 40k and 60k characters. Set each clip from that measure and record the numbers in the comment. Delete this file in that PR.
