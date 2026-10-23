# A session's temp folder goes after its transcript is idle 24 hours

## The rulings

Owner, 2026-10-16: the sweep removes a session's temp folder, `%TEMP%\claude\<project>\<session id>\`, once its transcript has been idle 24 hours. The owner chose it over a 7-day limit and over no sweep. A session resumed after a day loses its temp files. On that day these folders held 17 GB on the Windows PC. The step is `janitor/temp_sweep.py`. The machine-wide sweep of `the-janitor-is-one-machine-wide-sweep` runs it on Windows, in a preview and under `--confirm`.

1. The transcript decides. Idle means the transcript `projects/<project>/<session id>.jsonl` changed more than 24 hours ago. The folder's own mtime does not count.
2. Keep when unsure. No transcript, an unreadable one, a live session process, an unreadable sessions folder, or a link in the path means keep.
3. Reach. Only a direct child of `Temp\claude\<project>\` is removed. A path elsewhere in Temp is never touched. The sweep deadline stops the step.
4. Cost. Process starts: none. Files removed: the idle session folders. How often: each sweep run on Windows.

Kind: process
Home: janitor/temp_sweep.py
