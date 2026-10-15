# Concurrent appends to the feedback inbox can drop lines

- **What.** On Windows, two processes that append with `open(..., "ab")` at the same time lost 406 of 8000 lines in a stress test. The hook and the judge child both append to the inbox, so a rare overlap can drop an owner message or a note item.
- **Where.** The inbox appends in `hooks/local_time.py` and `hooks/feedback_judge.py`.
- **Decision.** `owner-feedback-inbox`.
- **Retire.** Serialize inbox appends with a lock file or one writer, and a stress test shows no lost lines.
