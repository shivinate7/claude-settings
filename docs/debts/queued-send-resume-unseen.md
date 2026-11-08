# A queued message that auto-resumes an agent may leave the run unwatched

**What.** A SendMessage queued to a running agent that finishes first auto-resumes it. Whether the main transcript then writes a resume record is unmeasured, so that run may stay unwatched: a quiet agent is never listed. Claude sends a message to a running agent in normal work.

**Where.** `hooks/stall_watch.py`, `scan_jobs`: only a `user` record whose `toolUseResult` dict has `resumedAgentId` reopens a closed agent.

**Decision.** stall-watch (a stalled background command is reported, never stopped).

**Retire.** Measure what a queued message to an agent that finishes first writes to the main transcript. If it writes a resume record, close this debt with a case in `hooks/test_stall_watch_stop.py`. If not, make `scan_jobs` reopen on what it does write, with a case that shows the run listed when quiet.
