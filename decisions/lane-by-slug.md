# A lane is named by its branch slug, not a session number

## The ruling

Owner, 2026-10-13 14:13 CDT, relayed by the oversight session: the guard refuses a session number that names a lane, such as `N20` or `(N16)`. Name the lane by its branch slug, such as `lane-number-cite`.

- The refusal covers four acts: a `git commit` message, a `gh pr create` body or title, a `gh pr edit` body or title, and a `gh pr merge` subject or body.
- `LANE_NUMBER` in `hooks/guard.py` is `\bN\d{1,3}b?\b`. It reads the same message text as the cite-by-id rule, for the message, body, file and title flags.
- Matches: `N20`, `N3b`, `(N16)`, `Lane N16`, `N1-N6`. Case-sensitive: `n20` passes. Four or more digits pass: `N1234`. Not a lane: `NaN`, `N/A`, `IPv4N1`, `N100000`, `N+1`.
- Quoted text is blanked first: a backtick code span on one line, and a fence opened by three backticks.
- A message file that cannot be read passes this rule. Cite-by-id refuses an unread file.
- A PowerShell call is judged the same way.
- An echo, a grep, a log search, a git note, a tag message and a PR list search are not messages, so they are allowed. A bare squash merge, and a merge subject that names a slug, are allowed.

Why: same class as CLAUDE.md `git-slug-then-claim-number`. A session number is handed out in one chat and means nothing outside it. A branch slug names the same lane for every reader.

Protected by the `lane-by-slug` block in `hooks/test_guard.py`.

Kind: process
Home: hooks/guard.py
