# The Windows liveness arm is proven only with a stub

- **What.** The repository has no Windows machine to run the Windows arm on. The arm's branching is proven with a stubbed `ctypes.windll` in `hooks/test_guard.py`, not with a real kernel32 call. That covers error 87, error 5 and a valid handle. A green Windows CI job is the read that proves the arm on the real platform. That job lands in a parallel change.
- **Where.** The Windows arm of `_process_start_ms` in `hooks/guard.py`.
- **Decision.** `liveness-read-is-platform-specific-and-unreadable-is-not-death` (the liveness read is platform-specific, and unreadable is not death).
- **Retire.** A green Windows CI job runs the arm against the real kernel32 call.
