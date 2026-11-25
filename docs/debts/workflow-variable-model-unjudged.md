# A Workflow call with a variable model is not judged

- **What.** `spawn_inputs` in `hooks/guard.py` drops a Workflow `agent()` call whose `model` or `agentType` the scan cannot read, such as a variable or a constant that holds the model. The model and role checks never judge that spawn, so a builder whose variable holds an Opus model passes. Workflow scripts often keep the model in a constant, so Claude is likely to hit this. Harm: an Opus spend the owner did not grant.
- **Where.** `spawn_inputs` in `hooks/guard.py` (about line 5224), its `unseen & {"model", "agentType"}` skip (about line 5244).
- **Decision.** `agent-model-cap` (the model cap). Its skip rule is the owner's ruling of 2026-11-01 11:43 CST (waiting-page item 107, pick a). That ruling covers a call the scan cannot read. A change that refuses such a call reverses it.
- **Retire.** Two paths. Resolve a simple constant in the script, which fits the ruling. Or refuse a call whose `model` or `agentType` the scan cannot read, which needs the owner's grant first. Either path adds a case to `hooks/test_guard.py` that is red on the current code and green after the fix. Runnable: `hooks/test_guard.py`.
