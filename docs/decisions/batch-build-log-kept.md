# A batch build keeps its log under the config dir's state folder

## The ruling

`merge --batch-build NAME` writes a log at `<config dir>/state/batch-build/NAME.log`, opened for append when the build starts.

1. The log holds a start line (batch name, lanes) and each line the build prints, flushed as it goes.
2. A `--ready` run hands ci-job that log as its `VERDICT_LOG`, so each lint step's output lands in it. The lane lint and the draft step keep today's behaviour outside a batch build.
3. A ci-job that does not finish in `LINT_SECONDS` writes `ci-job did not finish in N s` to the log, and the Stop text names the log's path.
4. The build keeps the newest 20 logs in the folder and removes the rest.
5. A log that cannot be opened prints one stderr line naming its path. The build goes on without it.

Cause, most likely and unmeasured: a `--ready` lint timed out at 3600 s and printed no log path. ci-job's own files sat in the session's temp folder, which `janitor/temp_sweep.py` removes once the transcript is idle 24 hours on Windows (decision `windows-temp-sweep`). The evidence was gone when the runner looked. This record did not re-read that run.

Home: `state/` is removed by no sweep. Checked with `grep -rn "batch-build\|state/" janitor/*.py hooks/*.py`: the janitor and the hooks name only their own files in `state/` (for example `agent-end-payloads.jsonl`, `sim-boots.jsonl`, `janitor-runs.jsonl`). None removes the folder or `batch-build/`.

Named reader: the batch runner, after a dead or failed build, then the retrospective.

Cost: one file per build, 20 kept, no process and no timer. The running merge writes it and prunes it.

Where it lives: `merge/merge.py`, `batch_build_log_path` (the path), `batch_build_log` (open, prune), `say` (mirror), `ci_job_run` (`VERDICT_LOG` and the timeout line).

Kind: process
Home: merge/merge.py
