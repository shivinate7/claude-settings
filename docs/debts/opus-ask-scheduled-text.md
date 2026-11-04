# A scheduled task's text may reach the plain Opus ask judge

**What.** A fired scheduled task or `send_later` message may reach the UserPromptSubmit hook with no notice tag. Its text is Claude's or a stored prompt, not the owner's typed words. If that text holds a plain Opus ask such as "send opus judges", the judge may grant an Opus override. Review round 1 of lane opus-plain-ask found this. It is not yet confirmed: no fired task's prompt has been read.

**Where.** `hooks/override.py` `grant_opus_ask`, and the notice check through `shared_names.MACHINE_TAGS`.

**Decision.** `owner-override` (the owner override and its Opus form).

**Retire.** Read one fired scheduled task's user event (`list_events`, kind user) and name the tag or frame it carries. If it carries one, add that frame to `MACHINE_TAGS`, with a test in `hooks/test_local_time.py`: a prompt in that frame that holds "send opus judges" makes no judge call. If it carries none, close the debt with that finding in `owner-override`.
