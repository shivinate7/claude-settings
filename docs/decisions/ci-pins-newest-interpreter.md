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

- Since commit 638d672ffb (2026-09-16, the first commit that set a Python pin), CI pins Python 3.11 on 40 lines: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. No reason is on record.
- The owner's Mac runs Python 3.15.
- On macOS, `os.waitid` is missing before Python 3.13 (`lint/test_verdict.py:48`). A macOS run on 3.11 lacks it; the owner's 3.15 Mac has it. Pull request 3869 (branch `hang-stop-zombie-no-waitid`) is the fix for the hang check that reads it.

## State

- Main still pins 3.11.
- Lane `ci-python-pin-moves` moves the pin. The consultant's plan: try 3.15 first, then 3.12, and pin the newest that passes its checks. Any fallback reason is written here.
- The floor for product code stays 3.9, checked by `lint/check_python_floor.py`.
- Unknown: the Python on the owner's Windows machine and in cloud sessions.

## Related

- Decision `action-pins-follow-sessions`: when CI and the session differ, the pin moves.
- Decision `dependabot-security-only`: automatic bump PRs are for security fixes only.

Kind: process
Home: .github/workflows/checks.yml
