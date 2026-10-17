# A sweep of idle session temp folders on Windows

**What waits.** A janitor step that deletes a session's temp folder,
`%LOCALAPPDATA%\Temp\claude<project><session id>\`, once that session's transcript in
`~/.claude/projects` has been idle 24 hours. On 2026-10-16 these folders held 17 GB on the
Windows PC.

**Owner ruling, 2026-10-16 23:52 CDT.** Sweep after 24 hours idle. The owner chose it over a
7-day limit and over no sweep. A session resumed after a day loses its temp files.

**Why it waits.** It runs only on Windows, and this session is on a Mac. The step needs red
cases. An idle folder goes. A folder whose transcript changed in the last 24 hours stays. A
folder with no transcript found stays, because an unknown read is never clear.

**What keeps it from being lost.** This file.

**Trigger.** The next session on the Windows PC.
