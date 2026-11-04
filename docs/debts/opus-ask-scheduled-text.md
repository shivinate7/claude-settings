# A create_session seed prompt may reach the plain Opus ask judge

**What.** The seed check in `grant_opus_ask` skips a prompt with no earlier owner turn in a cloud session. Two points are unmeasured. The first: whether the transcript already holds the current prompt when UserPromptSubmit fires. The second: whether an untagged `create_session` prompt is stored with `isMeta` or a non-human `origin`. If the transcript holds the seed as a plain record, the seed counts as its own owner turn, and a Claude-written Opus ask in it reaches the judge. The haiku judge granted on 3 of 10 Claude-written texts (review round 3). Measured: a seed sent by `send_message` is `isMeta` with `origin.kind` peer, and a fired scheduled task carries a `<system-reminder>This task fired at` block. Both grant nothing.

**Where.** `hooks/override.py` `_owner_turn_in` and `grant_opus_ask`.

**Decision.** `owner-override` (the owner override and its Opus form).

**Retire.** Start one cloud session with an untagged `create_session` prompt. Read its first user record's `isMeta` and `origin`, and whether that record is in the transcript when UserPromptSubmit fires. If the record counts as an owner turn, change the seed check to skip it, with a test in `hooks/test_local_time.py`. Else close this debt.
