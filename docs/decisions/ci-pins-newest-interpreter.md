# CI pins the newest Python that passes its checks

## The ruling

Owner, 2026-11-24 20:38 CST, typed in the consultant's chat, agreeing to the pick "CI pins the newest Python that passes its checks":

"agreed, and all repos would likely adopt this too, but if for whatever reason a specific repo needs older ci, it would have to make an explicit carve out to say so, kind of like my ruling that repos have to always obey claude-settings unless they're explicitly called out on"

Owner, 2026-11-25 10:19 CST, typed in the consultant's chat:

"i didnt say that at all? i said this concept of pins aligning between whats tested and whats worked on needs to be done for all repos, not that all repos need python 3.15 pinned forcefully... and remember i'm just trying to voice the conceptual here"

Owner, 2026-11-25 10:19 CST, on question QAF (git versions on the Mac and Windows machines), option a ("install the pinned git on your Mac with Homebrew and upgrade Git for Windows"): "this". The grant covers that act.

## What it means

The consultant reads the rulings this way; the owner's words are quoted above.

- Each repo states its own tool versions once. Its CI and its people's machines both match that statement. The values are each repo's own; no repo is forced to 3.15.
- A repo's default Python is the newest that passes its checks. This applies rule `verification-newest-that-passes` (CLAUDE.md, "take the newest version that passes its checks").
- A repo that needs an older Python makes an explicit carve-out, with its reason. Silence means newest.

## The mistake and its harm

- CI carries its Python pin as 40 literal copies: 38 in `.github/workflows/checks.yml`, 2 in `.github/workflows/lane-touched-tests.yml`. All 40 say 3.15.
- Nothing moves the pin. Each bump is a hand edit of 40 lines.
- The owner's Mac runs Python 3.15. On macOS, `os.waitid` is missing before Python 3.13 (`lint/test_verdict.py:48`), so a pin below 3.13 runs that check without it.

## State

- Main pins 3.15 on all 40 lines. Nothing moves the pin yet.
- Lane `ci-python-pin-follows-newest` gives the pin one home. The daily run tries the next Python and says when it passes (no new timer). Other repos take the same concept, with their own values.
- The lane waits on the open PRs that hold `.github/workflows/checks.yml`. Any fallback reason is written here.
- Git: Homebrew's git is 2.56.1 on Nov 25; Apple's was 2.54.0.
- The floor for product code stays 3.9, checked by `lint/check_python_floor.py`.
- Unknown: the Python on the owner's Windows machine and in cloud sessions.

## Related

- Decision `action-pins-follow-sessions`: when CI and the session differ, the pin moves.
- Decision `dependabot-security-only`: automatic bump PRs are for security fixes only.

Kind: process
Home: .github/workflows/checks.yml
