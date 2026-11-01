# A lane blocked on an approval reads as stale

- **What.** The roadmap's stale-step row counts a session as live only when its status is RUNNING or IDLE. A lane waiting on an approval reads `SESSION_STATUS_REQUIRES_ACTION` (seen Oct 30 on a live lane for step c104), so its step is listed `set to todo` while the lane works.
- **Where.** `skills/roadmap/build.py` `LIVE_SESSION`; test `skills/roadmap/test_build.py` StaleInProgress pins STOPPED and COMPLETED as not live, values not seen in real `list_sessions` data.
- **Decision.** none.
- **Retire.** `LIVE_SESSION` also holds `SESSION_STATUS_REQUIRES_ACTION`, with a red-then-green case in StaleInProgress for a lane in that status.
