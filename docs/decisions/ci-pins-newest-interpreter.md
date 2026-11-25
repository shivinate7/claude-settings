# CI pins the newest Python that passes its checks

## The ruling

Owner, 2026-11-24 20:38 CST, typed in the consultant's chat, on the pick "no Homebrew install; a lane moves CI's pin to the newest Python that passes, trying 3.15 first, then 3.12":

"agreed, and all repos would likely adopt this too, but if for whatever reason a specific repo needs older ci, it would have to make an explicit carve out to say so, kind of like my ruling that repos have to always obey claude-settings unless they're explicitly called out on"

## What it means

- CI pins the newest Python that passes its checks. This applies rule `verification-newest-that-passes` (CLAUDE.md, "take the newest version that passes its checks").
- Every repo follows this.
- A repo that needs an older Python makes an explicit carve-out, with its reason. Silence means newest.

## The mistake and its harm

- Since commit 638d672ffb (2026-09-16, the first commit that set a Python pin), CI pins Python 3.11 on 40 lines: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. No reason is on record.
- The owner's Mac runs Python 3.15.
- On 2026-11-24 a bug that shows only on 3.11 (no `os.waitid` on macOS) passed locally. It showed only in a hand-started full CI run. Pull request 3869 (the fix) resolved it.

## State

- Main still pins 3.11.
- Lane `ci-python-pin-moves` moves the pin to 3.15. If a check breaks on 3.15, the lane pins the newest Python that passes and writes the reason here.
- The floor for product code stays 3.9, checked by `lint/check_python_floor.py`.
- Unknown: the Python on the owner's Windows machine and in cloud sessions.

## Related

- Decision `action-pins-follow-sessions`: when CI and the session differ, the pin moves.
- Decision `dependabot-security-only`: automatic bump PRs are for security fixes only. So a session, not a bot, moves an interpreter pin.

Kind: process
Home: .github/workflows/checks.yml
