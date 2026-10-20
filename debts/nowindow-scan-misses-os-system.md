# The no-window scan misses os.system

- **What.** lint/test_no_window_spawn.py reads subprocess and Node child_process calls only. os.system and os.popen pass unseen. Product code has none today.
- **Where.** lint/test_no_window_spawn.py.
- **Decision.** `spawns-use-no-window` (helper programs start with no window).
- **Retire.** The scan also flags os.system and os.popen. Check: a fixture with each goes red.
