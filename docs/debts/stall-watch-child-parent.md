# A hung parent over a long-lived child is never reported

**What.** A parent with a long-lived child reads as a waiter for its whole run, so the stall watch never reports it. A hung `playwright install` through its launcher is the shape. That is the incident that founded the stall watch. Which launcher form the incident used is unmeasured. Other cases: xdist workers, an MCP server, ssh ProxyJump, `git push` on a dead network.

**Where.** `has_waiter` and `runs_shell` in `hooks/stall_watch.py`, and the Stop check `busy_outputs`. Both count a non-shell process with a live child as life.

**Decision.** `stall-watch` (a stalled background command is reported, never stopped).

**Retire.** Report a waiter whose whole child tree has used no CPU and written no log for a long cap, and show it with a case in `hooks/test_stall_watch.py`. First measure the process tree of a hung `playwright install`.
