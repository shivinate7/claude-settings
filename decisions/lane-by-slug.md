# A lane is named by its branch slug, not a session number

## The question

May a commit message name a lane by its session number? Such as `N20` or `(N16)`. The same
question applies to a PR title or body, and to a `gh pr merge` subject or body.

## The ruling

Owner, 2026-10-13 14:13 CDT, relayed by the oversight session:

- The guard refuses a session number that names a lane. Name the lane by its branch slug,
  such as `lane-number-cite`.
- The refusal covers four acts. They are a `git commit` message, a `gh pr create` body or
  title, a `gh pr edit` body or title, and a `gh pr merge` subject or body.

It is the same class as CLAUDE.md `git-slug-then-claim-number`. A session number is handed
out in one chat. Outside that chat it means nothing. A branch slug names the same lane for
every reader.

## The incident

In q_max, commit titles on main carry session numbers. Each number was handed out in one
session's chat.

MEASURED 2026-10-13, `git log --since=2026-10-12 origin/main` in q_max, at 7fb885ef9: 32
subject lines match the pattern. 19 of them are non-merge commits. The relayed count, 12, was
not reproduced. This record uses the measured count.

## The match

`hooks/guard.py`, `LANE_NUMBER`, is `\bN\d{1,3}b?\b`. It reads the same message text as the
cite-by-id rule, for the message, body, file and title flags.

- Matches: `N20`, `N3b`, `(N16)`, `Lane N16`, `N1-N6`.
- Case-sensitive: `n20` passes.
- Four or more digits pass: `N1234` passes.
- Not a lane: `NaN`, `N/A`, `IPv4N1`, `N100000`, `N+1`.
- Quoted text is blanked first. That is a backtick code span on one line, and a fence opened
  by three backticks.
- A message file that cannot be read passes this rule. Cite-by-id refuses an unread file.
- A PowerShell call is judged the same way.

## What protects it

`hooks/test_guard.py`, the `lane-by-slug` block near line 4816. It covers:

- The refusal names a branch slug as the remedy.
- A commit message naming `N16` denies, from bash and from PowerShell. A `-F` file at a native
  path denies.
- A PR create title, and a PR edit title, naming a lane deny.
- A `gh pr merge` subject or body naming a lane denies.
- A number inside a code span or a fence is allowed.
- The false-positive cases (`NaN`, `N/A`, `IPv4N1`, `N100000`, `N+1`) are allowed.
- A bare squash merge is allowed. A merge subject that names a slug is allowed.
- An echo, a grep, a log search, a git note, a tag message and a PR list search are not
  messages, so they are allowed.

## Holes, named

Debts: `cite-by-id-skips-merge-subject` (cite-by-id does not read a `gh pr merge` subject), `lane-slug-lowercase-n-passes` (lowercase `n20` and four-digit numbers pass), `lane-slug-part-code-refused` (a part code such as `N12` is refused), `lane-slug-heredoc-untested` (the heredoc header reader has thin tests and no mutant), `guard-split-heredocs-here-string` (a here-string is read as a heredoc), `lane-slug-header-count-shift` (an interpreter body or a `case` shifts the header count), `lane-slug-piped-body-unread` (a piped commit body is not read). `lane-slug-tag-messages-unchecked` (tag messages are out of scope, and a tag is another act). `lane-slug-gh-m-flag-passes` (a session number after gh -m passes the rule).

## Named limits

- Old history is not checked. Only new acts are judged, so the 32 titles on q_max main stay.

## What reopens it

A session number reaches main through an act the guard does not read. Then widen the scan,
and name the new limit in this record.

Kind: process
Home: hooks/guard.py
