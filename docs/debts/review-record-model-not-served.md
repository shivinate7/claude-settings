# A review record names the model the lane typed, not the model that ran

- **What.** `merge --review-record` refuses a fix check or round 2/3 line that names a non-Sonnet model, but it takes the model as typed. A lane can still write `sonnet` for a reviewer that ran on its Haiku pin. The model an agent ran on is readable in its transcript (assistant lines carry `"model"`), but the merge tool has no path to that transcript.
- **Where.** `merge/merge.py` (`--round`, `--fix-check`, the `--review-record` branch).
- **Decision.** `agent-model-cap` (the reviewer rows; fix check on Sonnet, owner item 444 a).
- **Retire.** `--review-record` can read the served model from the agent's transcript (a `--served-from` input) and refuses a line whose model differs. A test shows a Sonnet-named line over a Haiku transcript refused.
