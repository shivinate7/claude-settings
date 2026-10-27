# From Triage (5), resolved

- Close c96 (main's full CI run ends green). Build advisor (6), Oct 27: all 85 cancelled main runs (Oct 13 to 27) were job timeouts, not newer pushes, and c61 (Windows jobs fit their caps) already fixed them: 4 of 6 main runs since are green; the 2 later cancels were hangs. It no longer blocks c95's pick. Their note is on c96 (roadmap 831751a).
- Watch, not yet a step: main's run on 2ad85de is red in the macOS stall-watch fixture suite (hooks/test_stall_watch.py case 23a, a known timing flake). If it repeats, file its own step.
- FYI: batch #652 needed two form fixes on lane branches (c78's record lacked a Plan line; c84's merge dropped a reworded line with no Drops-lines trailer); re-running.
- Close c84 (a question waiting on shiv never stops a session from orchestrating): PR 648 merged Oct 27, main e305bdb; its thread rewrote the note (roadmap 4ea81a6). Its follow-up check is already filed as c86.
