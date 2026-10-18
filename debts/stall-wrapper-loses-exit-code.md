# The stall watch cuts off a healthy silent run

- **What.** A background command that prints nothing for 300 s gets a STALL report, even when it is healthy, such as `python3 hooks/test_guard.py`. The wrapper then exits 3 and the job runs on detached. The session loses the job's exit code. This happened twice on 2026-10-18.
- **Where.** The wrapper line `[ $rc -eq 3 ] && exit 3` in `hooks/stall_watch.py`, and each long command that prints nothing, such as `hooks/test_guard.py`.
- **Decision.** `stall-watch` (a stalled background command is reported, never stopped). Its ruling puts the duty on the quiet tool: print a progress line at least every 120 s.
- **Retire.** Either `hooks/test_guard.py` and each other long silent command print a progress line at least every 120 s. Or the wrapper waits for the job after the report and returns the job's exit code; that changes the ruling, so it needs the owner's word. A test runs a job that is quiet past the quiet age and shows the session gets the job's own exit code.
