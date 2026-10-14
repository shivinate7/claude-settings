# A list result closes a job from its first block only

- **What.** A list-form result closes a job only from its first text block. A multi-block result closes a job only when `Successfully stopped task` sits in the first block.
- **Where.** The result reader in `hooks/stall_watch.py`.
- **Decision.** `stall-watch-stop-check` (the stall watch flags open jobs at Stop).
- **Retire.** Search every text block of a list result. A test with the phrase in the second block closes the job.
