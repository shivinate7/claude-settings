# Judge prompt clips are unmeasured

- **What.** The prompt now goes to `claude -p` on stdin, so no argv cap bounds it. `PROMPT_MAX_LEN` (20000), `REPLY_MAX` (12000) and `PROMPT_MAX` (150000) bound cost and latency only. None is measured beyond one sample: 150,000 chars on Haiku xhigh took 17 s, under the 90 s timeout.
- **Where.** `hooks/decision_watch.py` (`PROMPT_MAX_LEN`), `hooks/reply_judge.py` (`REPLY_MAX`), `hooks/question_outcome.py` (`PROMPT_MAX`).
- **Decision.** `question-outcome-check` (the judge checks if a question got its answer).
- **Retire.** Measure cost and latency of a judge call at 20k, 40k, 60k and 150k characters, several samples each. Set each clip from that measure and record the numbers in the comment. Delete this file in that PR.
