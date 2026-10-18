# Idle session temp folders on Windows are never swept

**What.** A session's temp folder, `%LOCALAPPDATA%\Temp\claude<project><session id>\`, is never deleted. On 2026-10-16 these folders held 17 GB on the Windows PC.

**Where.** `janitor/`: a new step. It runs only on Windows.

**Decision.** none. See the Ruling below.

**Retire.** Add the janitor step on the Windows PC, with red cases:

- A folder whose session transcript in `~/.claude/projects` has been idle 24 hours goes.
- A folder whose transcript changed in the last 24 hours stays.
- A folder with no transcript found stays (an unknown read is never clear).

The next session on the Windows PC builds it.

## Ruling

Owner, 2026-10-16 23:52 CDT: sweep a session's temp folder after its transcript has been idle 24 hours. The owner chose it over a 7-day limit and over no sweep. A session resumed after a day loses its temp files.
