# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2B6FrRWBCF8RWpq8y

## Reply at 2026-11-10T17:26:48Z UTC

IDLE (B)
Goal: roadmap step ci-macos-idle-measure (measure idle macOS runner minutes). Measure, from 14 days of Actions history, the macOS runner minutes that docs-only PRs spend idle. Ask the owner only if the cost is real.
State: done. Nothing is running, and everything is pushed.
PR #1571 (Measure idle macOS minutes on pull requests): branch ci-macos-idle-measure, head ad6697c8b, still an open draft. Handed to runner 8 on 2026-11-07 15:50 CST.
Review: round 1 FAIL (Haiku reviewer), round 2 FAIL (Sonnet reviewer). The round-2 wording fixes passed their fix check.
Files: docs/decisions/ci-job-caps.md, which gives the figures and holds the script in How to measure again, item 7. docs/debts/notes.md, where the note checks-macos-b-idle-runner (idle macOS runner) is deleted.
Figures: 2026-10-24 to 2026-11-06 UTC, every rerun attempt counted.
- claude-settings: 41 idle macOS jobs, 55 min, 0.5% of its 10370 macOS min on PR runs.
- All four repos whose PRs used macOS: 74 idle jobs, 134 min.
- Private repos (home, ios-adblock): $0.56. Public repos run free.
- No real cost, so the owner was asked nothing.
Left:
- The batch runner merges #1571.
- Triage closes the roadmap step.
- Lane notes-fix-merge-ci edits the same note and will conflict with #1571.

