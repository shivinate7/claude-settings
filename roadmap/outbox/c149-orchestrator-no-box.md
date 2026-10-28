# c149-orchestrator-no-box

- c149: done, draft PR #729 at b15addf. Builds on merged PR #665 (session-board refuses the box while work runs), in the same check. A successful start_session or create_session refuses the box for the rest of the session. Red, then 144/144 green. Local gates pass. 3 review rounds; net value positive. Ready for the next batch.
- c149 note (low, for docs/debts/notes.md): session-board keeps a `started:` record forever when its `sess:` entry exists but cannot be read.
- c149 note (low): an orchestrator stopped over a day ago may lose its started count at the next sweep, so a resume reopens the box. The record lists this under "Not covered".
