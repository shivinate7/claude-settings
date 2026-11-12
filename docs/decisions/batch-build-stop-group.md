# A stopped batch build pushes nothing

Kind: process
Home: merge/merge.py

## The ruling

A batch build that its runner stopped never pushes the batch branch or writes its pull request body. Step `batch-build-stop-group`.

Incident (11:14 to 11:16 CST Nov 12): runner 10 ran `kill` on the build's pid. The pid went away, yet the build pushed batch-104.

Measured: the chain is the `merge` shim, then `merge/launch.py`, then `merge/merge.py`, then `bin/ci-job`, then git. The push is a git child of `merge.py`. A `kill` of the shim leaves the other three running, and `merge.py`'s parent stays alive, so a parent check misses it. The build has no process group of its own: all four sit in the caller's group.

Fix (built): `bin/merge` sets `CLAUDE_MERGE_SHIM_PID` to its own pid for the child it starts, and `launch.py` passes the environment on. `merge.py` main records the shim pid (when set and numeric) and `os.getppid()` (the launch link) before a batch command runs. `build_integration_branch` calls `build_stopped` on them before it writes the body and before it pushes, and stops with "Nothing was pushed" when one is gone. Build, drop, the lease heal and restack all go through it. Nothing kills a tree. The check uses `pid_alive`, which works on Windows. A group stop was rejected: it needs a new group, has no Windows form, and would hit the caller's shell.

Stop route today (measured 11:32 CST Nov 12, coordinator-confirmed): a runner stops a build one pid per call, top-down: the shim, then `launch.py`, then `merge.py`, then `ci-job`. The kill guard (`foreign_pid_kill`) owns a pid whose parent is init and whose environment holds the session tag, and a child of that pid then has an init-parented parent too. A combined `kill` of all links in one call is refused by design while a child's grandparent is not init. After the fix, stopping the shim alone is enough: the build stops itself before it pushes.

Differs from `stall-watch` line 6, which rejects a whole-tree kill by the stall watch: here no process is killed. The build stops itself.

Limits: a reused pid reads alive; the lint of a stopped build still runs to its cap.
