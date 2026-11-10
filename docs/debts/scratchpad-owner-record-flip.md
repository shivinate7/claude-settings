# A denied overwrite moves the record to the asker

- **What.** The record is written before the overwrite ask, so a denied ask still moves the record to the asker. The asker's retry then passes, and it runs the first writer's file unasked, which runs the first writer's code. The first writer is asked on each of its own runs until it rewrites the file. Probed: A writes f.py; B's overwrite is asked and denied; B's retry is allowed; B runs `python3 f.py` unasked (the run incident of decision `scratchpad-owner`).
- **Where.** `hooks/guard.py` `scratchpad_owner_write`: it calls `scratchpad_record_writer` before the taken ask is refused.
- **Decision.** `scratchpad-owner` (an agent asks before it runs or overwrites another agent's scratchpad file).
- **Retire.** Fix: keep the previous writer, and judge by it while the file's mtime is older than the record. Check: a case in the scratchpad-owner family of `hooks/test_guard.py` where B's denied overwrite leaves A as the writer, B's retry is asked, and B's run of A's file is asked: `hooks/test_guard.py`.
