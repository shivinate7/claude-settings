# Todo

Tasks a session caught and did not do. One line each.

- Merge c136, one page per repo (waiting on you first, the roadmap below). Owner asked its status Oct 28 13:04 CDT and Oct 29 13:44 CDT. Lane started Oct 29.
- Align each child repo (banchi, q_max, home, mailaudit, degen) with claude-settings main, under grant item 2 a. Fix lanes started Oct 29 (owner asked 13:45 CDT); each repo's PR needs its batch runner to merge.
- fb-1520-1: Running /autocompact writes the chosen window into the user settings file. In the pinned checkout that file is the tracked settings.json, so the repo shows a stray change (measured Oct 28, Claude Code 2.1.312). Keep that write off the tracked file. The hook half is done: the handoff hook reads the window in use (decision precompact-handoff, item 1). Roadmap step c203 (compact window off the tracked file) is marked done, but only the hook half shipped. The fix route waits on the owner's answer to waiting-page item 61 (per-tier context limits, still open); its option c is a settings.json copy made at install.
