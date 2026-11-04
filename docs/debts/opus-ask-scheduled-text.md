# A seed prompt or a timed check-in may reach the plain Opus ask judge

**What.** `grant_opus_ask` refuses a prompt whose own transcript record has `promptSource` `system`, and in a cloud session a prompt with no earlier owner turn. Both rest on record shapes that are unmeasured at hook time. Is a timed check-in's record (CronCreate, ScheduleWakeup) in the transcript when UserPromptSubmit fires, and does it carry `promptSource` `system`? Is a `create_session` seed's record there, equal to the hook's prompt? If not, a Claude-written Opus ask in that text reaches the judge. The haiku judge granted on 3 of 10 such asks (review, 2026-11-03).

**Where.** `hooks/override.py` `_system_prompt_last`, `_owner_turn_in` and `grant_opus_ask`.

**Decision.** `owner-override` (the owner override and its Opus form).

**Retire.** Read the UserPromptSubmit payload's `source` field, which the Claude Code 2.1.318 schema names: `user`, `sdk`, `system`, `loop_wakeup`, `schedule_wakeup` or `poll_event`. A payload may still omit it. Refuse a plain ask unless `source` is `user` or absent, with a test for each value in `hooks/test_local_time.py`. Keep the transcript read as the fallback when the field is absent. Then close this debt.
