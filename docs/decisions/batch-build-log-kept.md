# A batch build keeps its log under the config dir's state folder

## The ruling

`merge --batch-build NAME` writes a log at `<config dir>/state/batch-build/NAME.log`, opened for append when the build starts.

1. The log holds a start line (batch name, lanes), written before the build's first read, each `say()` line the build prints, flushed as it goes, and one end line: `end: ok`, `end: refused: <first line of the Stop>`, or `end: failed: <first line of the error>` (the error is raised again; a non-zero exit reads `end: failed: exit N`). A SIGKILL leaves no end line, by design: a log with no end line is a build that was killed.
2. A `--ready` run hands ci-job that log as its `VERDICT_LOG`, and `TMPDIR`, `TEMP` and `TMP` set to `state/batch-build/NAME.tmp/`, which the build makes. ci-job's own files, the parallel lint steps' output included, sit under `state/` as they are written. So no step output waits for the end to reach the log, and a kill at the timeout loses none. The lane lint and the draft step keep today's environment outside a batch build.
3. A ci-job that does not finish in `LINT_SECONDS` writes `ci-job did not finish in N s` to the log, and the Stop text names the log's path.
4. The build keeps the newest 20 logs in the folder and removes the rest, each with its `NAME.tmp/` folder. It never removes its own.
5. A log that cannot be opened prints one stderr line naming its path. The build goes on without it.

Cause of the death of batch 104's first build: unmeasured. That build ran in a Linux cloud container and ended at about 10:24 CST with nothing pushed. What is known is that the build wrote no log of its own, so its output lived only in the session and was lost with it. This record did not re-read that run.

A second, separate gap: a `--ready` lint that times out at 3600 s prints no log path. ci-job's own files sit in the session's temp folder, which `janitor/temp_sweep.py` removes once the transcript is idle 24 hours on Windows (decision `windows-temp-sweep`). That sweep did not remove batch 104's log: that run was not on Windows.

Its home is `state/`: no sweep removes it. Checked with `grep -rn "batch-build\|state/" janitor/*.py hooks/*.py`: the janitor and the hooks name only their own files in `state/` (for example `agent-end-payloads.jsonl`, `sim-boots.jsonl`, `janitor-runs.jsonl`). None removes the folder or `batch-build/`.

Named reader: the batch runner, after a dead or failed build, then the retrospective.

Cost: one log and one temp folder per build, 20 of each kept, no process and no timer. The folder holds ci-job's own temp files. The running merge writes the log and prunes both.

Where it lives: `merge/merge.py`, `batch_build_log_path` (the path), `batch_tmp_path` (the folder), `batch_build_log` (open, prune), `prune_batch_logs`, `batch_build` (start and end lines), `say` (mirror), `ci_job_run` (`VERDICT_LOG`, the temp variables and the timeout line).

Kind: process
Home: merge/merge.py
