# A quoted script for an unnamed runner is unread

- **What.** A wide `rm -rf` or a `tail -f` inside a quoted script for a runner the guard does not name passes, such as `docker run img sh -c 'rm -rf /'`.
- **Where.** `hooks/guard_push_delete.py`, `hooks/guard_stream.py`.
- **Decision.** `guard-reads-wrapped-commands` (the stream and delete guards read the command a wrapper runs).
- **Retire.** Read every quoted argument that follows `-c` as a script.
