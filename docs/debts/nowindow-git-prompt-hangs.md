# A git terminal prompt hangs with no window

- **What.** A git credential prompt on the terminal, from merge/merge.py sh(), has no console to show in, so it would wait with no end. Unmeasured.
- **Where.** merge/merge.py, sh().
- **Decision.** `spawns-use-no-window` (helper programs start with no window).
- **Retire.** Measure a terminal credential prompt under sh(). If it hangs, set GIT_TERMINAL_PROMPT=0 there.
