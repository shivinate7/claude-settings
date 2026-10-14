# No retry runs inside the shared deadline

- **What.** No retry runs inside `shared_deadline`, which wraps the guard's head read. `Host.gh` sets the retry count to 0 there. A network error there reads as unknown.
- **Where.** `shared_deadline` and `Host.gh` in `merge/merge.py`.
- **Decision.** `merge-net-retry` (what bin/merge does when a network error stops a call).
- **Retire.** A network error inside `shared_deadline` retries as the other calls do, and a case pins it.
