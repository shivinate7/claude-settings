# CI pins the newest Python that passes its checks

## The ruling

Owner, 2026-11-24 20:38 CST, typed in the consultant's chat, agreeing to the pick "CI pins the newest Python that passes its checks":

"agreed, and all repos would likely adopt this too, but if for whatever reason a specific repo needs older ci, it would have to make an explicit carve out to say so, kind of like my ruling that repos have to always obey claude-settings unless they're explicitly called out on"

The owner expects all repos to adopt it ("would likely adopt"). A repo that needs an older CI interpreter must write an explicit carve-out.

## What it means

The consultant reads the ruling this way; the owner's words are quoted above.

- CI pins the newest Python that passes its checks. This applies rule `verification-newest-that-passes` (CLAUDE.md, "take the newest version that passes its checks").
- A repo that needs an older Python makes an explicit carve-out, with its reason. Silence means newest.

## The mistake and its harm

- CI carries its Python pin as 40 literal copies: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. All 40 say 3.15.
- Nothing moves the pin. Each bump is a hand edit of 40 lines.
- The owner's Mac runs Python 3.15. On macOS, `os.waitid` is missing before Python 3.13 (`lint/test_verdict.py:48`), so a pin below 3.13 runs that check without it.

## State

- Main pins 3.15 on all 40 lines. Nothing moves the pin yet.
- Lane `ci-python-pin-follows-newest` gives the pin one home. The daily run tries the next Python and says when it passes (no new timer). Other repos take the same pin, with an explicit carve-out.
- The lane waits on the open PRs that hold `.github/workflows/checks.yml`. Any fallback reason is written here.
- The floor for product code stays 3.9, checked by `lint/check_python_floor.py`.
- Unknown: the Python on the owner's Windows machine and in cloud sessions.

## Related

- Decision `action-pins-follow-sessions`: when CI and the session differ, the pin moves.
- Decision `dependabot-security-only`: automatic bump PRs are for security fixes only.

Kind: process
Home: .github/workflows/checks.yml
