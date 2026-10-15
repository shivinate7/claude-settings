# The stall status match is case-sensitive

- **What.** The status match is case-sensitive. A status outside the list counts as open. A job with a new or differently cased status never closes.
- **Where.** The status list in `hooks/stall_watch.py`.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Match status without regard to case, and add each new final status to the list. A test with a mixed-case final status closes the job.
