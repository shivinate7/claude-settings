# The mailbox time bounds are unproven on Windows

- **What.** On Windows, `subprocess.run` calls `communicate()` after a timeout, which waits for any helper child that still holds the pipe. So the 3, 4, 2 and 1 s bounds may not hold (unmeasured). `hooks/local_time.py` `main` does not flush the time line before `mail_lines`, so a hook killed at 30 s loses the time line as well. On POSIX the 10 s bound holds.
- **Where.** `hooks/mail.py` `git`; `hooks/local_time.py` `main`.
- **Decision.** session-messages (messages to and from sessions).
- **Retire.** A case in `hooks/test_local_time.py` shows the time line is printed and flushed before `mail_lines` runs, and build step 2 measures a hung remote on Windows within the 10 s bound.
