# A review record names the model the lane typed, not the model that ran

- **What.** `merge --review-record` refuses a non-Sonnet fix check or round 2/3 line, but only reads the model as typed. A lane can write `sonnet` for a reviewer that ran on Haiku, and `review_state` still reads any posted Haiku record as done. The agent's transcript holds the served model (assistant lines carry `"model"`), but the merge tool cannot reach it.
- **Where.** `merge/merge.py` (`--round`, `--fix-check`, the `--review-record` branch; `review_state` and the merge gate, which read posted records).
- **Decision.** `agent-model-cap` (the reviewer rows; fix check on Sonnet, owner item 444 a).
- **Retire.** `--review-record` reads the served model from the agent's transcript (`--served-from`) and refuses a line that differs. The merge gate also refuses a posted round 2/3 or fix check record that names a non-Sonnet model. Tests in `merge/test_merge.py` show a Sonnet-named line over a Haiku transcript refused, and a posted round 2 Haiku record not read as done.
