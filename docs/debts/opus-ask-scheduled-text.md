# Text from no owner may reach the plain Opus ask judge

**What.** A fired scheduled task or `send_later` message may reach the UserPromptSubmit hook with no notice tag. Its text is Claude's or a stored prompt, not the owner's typed words. If that text holds a plain Opus ask such as "send opus judges", the judge may grant an Opus override. A seed prompt (the first prompt one session sends a new session) has the same risk. The seed check in `grant_opus_ask` blocks it only if the transcript does not yet hold the current prompt when UserPromptSubmit fires, and that is unmeasured. Review rounds 1 and 2 of lane opus-plain-ask found this. Neither is confirmed.

**Where.** `hooks/override.py` `grant_opus_ask`, and the notice check through `shared_names.MACHINE_TAGS`.

**Decision.** `owner-override` (the owner override and its Opus form).

**Retire.** Start one cloud session with a seed prompt, and read whether its transcript holds that prompt at UserPromptSubmit. If it does, change the seed check to look for an owner turn before the current one, with a test. Read one fired scheduled task's user event (`list_events`, kind user) and name the tag or frame it carries. If it carries one, add that frame to `MACHINE_TAGS`, with a test in `hooks/test_local_time.py`: a prompt in that frame that holds "send opus judges" makes no judge call. If it carries none, close the debt with that finding in `owner-override`.
