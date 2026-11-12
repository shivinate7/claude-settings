# A stopped batch build pushes nothing

Kind: process
Home: merge/merge.py

## The ruling

A batch build that its runner stopped never pushes the batch branch or writes its pull request body. Step `batch-build-stop-group`.

Incident (11:14 to 11:16 CST Nov 12): runner 10 ran `kill` on the build's pid. The pid went away, yet the build pushed batch-104.

Measured: the chain is the `merge` shim, then `merge/launch.py`, then `merge/merge.py`, then `bin/ci-job`, then git. The push is a git child of `merge.py`. A `kill` of the shim leaves the other three running, and `merge.py`'s parent stays alive, so a parent check misses it. The build has no process group of its own: all four sit in the caller's group.

Fix (built): `bin/merge` sets `CLAUDE_MERGE_SHIM_PID` to its own pid for the child it starts, and `launch.py` passes the environment on. `merge.py` main records the shim pid (when set and numeric) and `os.getppid()` (the launch link) in `BUILD_LINKS` before a batch command runs. `refuse_if_stopped` checks them with `pid_alive`, which works on Windows, and stops with "Nothing was pushed" when one is gone. The check runs in `build_integration_branch` before the body write and again before the push (inside the try, so a stopped push puts the old body back), and in `batch_build --ready` before the Linted stamp. Build, drop, the lease heal and restack all go through `build_integration_branch`. Nothing kills a tree. A group stop was rejected: it needs a new group, has no Windows form, and would hit the caller's shell.

Stop route today (measured 11:32 CST Nov 12, coordinator-confirmed): a runner stops a build one pid per call, top-down: the shim, then `launch.py`, then `merge.py`, then `ci-job`. The kill guard (`foreign_pid_kill`) owns a pid whose parent is init and whose environment holds the session tag, and a child of that pid then has an init-parented parent too. A combined `kill` of all links in one call is refused by design while a child's grandparent is not init. After the fix, stopping the shim alone is enough: the build stops itself at its next check.

Differs from `stall-watch`, which rejects stopping the stuck command: this build kills nothing. The build stops itself.

Limits:
- A kill that lands during git's own push, after the last check, still pushes.
- `pid_alive` reads a killed-but-unreaped or SIGSTOPped pid as alive, and a reused pid as alive.
- A direct `merge.py --batch-build` whose parent exited reads stopped.
- A non-numeric `CLAUDE_MERGE_SHIM_PID` skips the shim check.
- An empty `BUILD_LINKS` gates nothing. Every caller sits under main's batch branch today.
- The lint of a stopped build runs to its cap.
