# A session's temp folder goes after its transcript is idle 24 hours

## The rulings

Owner, 2026-10-16: the sweep removes a session's temp folder, `%TEMP%\claude\<project>\<session id>\`, once its transcript has been idle 24 hours. The owner chose it over a 7-day limit and over no sweep. A session resumed after a day loses its temp files. On that day these folders held 17 GB on the Windows PC.

Owner, 2026-11-17 13:30 CST, on the own-leftover cleanup goal (`tools-clean-own-leftovers`): the step runs on every OS, Linux and Mac as well as Windows.

The step is `janitor/temp_sweep.py`. The machine-wide janitor sweep (`the-janitor-is-one-machine-wide-sweep`) runs it, in a preview and under `--confirm`. It runs in each full sweep that is inside its deadline: the daily job, a person's full run and the SessionEnd run.

1. The transcript decides. Idle means that the transcript `projects/<project>/<session id>.jsonl` changed more than 24 hours ago. The folder's own mtime does not count.
2. When unsure, keep. No transcript, an unreadable one, or one dated in the future means keep. So does a live session process, an unreadable sessions folder or session reader, or a link in the path.
3. Reach. Only a direct child of `<Temp>\claude\<project>\` (Windows) or of `<tempdir>/claude-<uid>/<project>/` (Linux and Mac) is removed. A path elsewhere in Temp is never touched, and neither is `claude-<uid>-old`. The sweep deadline stops the step.
4. Cost. Process starts: none on Windows. On Linux and Mac, one `ps` per session record that has a pid and a start time, to read the session's start (`hooks/git_reads.py`, `session_is_live`). Files removed: the idle session folders. How often: each full sweep run inside its deadline, on every OS. Cost test: none names the `ps` count.

Kind: process
Home: janitor/temp_sweep.py
