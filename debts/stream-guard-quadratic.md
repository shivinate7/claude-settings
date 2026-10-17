# A long segment is slow

- **What.** The stream guard slices the word list once per bare word. A 20,000-word segment takes 8.2 s.
- **Where.** `hooks/guard_stream.py`.
- **Decision.** `guard-reads-wrapped-commands` (the stream and delete guards read the command a wrapper runs).
- **Retire.** Scan the words once.
