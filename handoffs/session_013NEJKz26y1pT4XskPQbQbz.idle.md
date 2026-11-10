# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKz26y1pT4XskPQbQbz

## Reply at 2026-11-10T17:23:06Z UTC

IDLE (B) — lane record-post-runs-lane-lint (topic merge-tool).
Goal: `merge <pr> --review-record` runs the existing lane lint on the reviewed head, and prints the record only when the lint passes. This stops a repeat of #1687, the PR that got a review record on head db9a31f and then failed the Hook catalog check in its batch.
State: draft PR #1760, branch record-post-runs-lane-lint, head 4c97367d58b3eaf904a4b102b9585f431d4de13d. Everything is pushed.
- The review record is posted (comment 6717438772): rounds 1 and 2 FAIL, round 3 PASS, guard or check yes, net value positive.
- `merge --lane-lint 1760` passed on that head (509.6 s).
- Handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) on 2026-11-07 at 22:52 CST. It is still not merged.
What it does:
- A FAIL or an unknown lint result refuses, and no flag lifts it.
- A repo with no checks job skips the lint and prints the record as main does.
- ci_job_run drops HOOK_CATALOG_ROOT from the lint's environment.
- The docs say to run `--review-record` in the background: the lint took 510 to 691 s (2 runs), and a foreground command is capped at 600 s.
Files: merge/merge.py, merge/test_lane_lint.py, merge/test_merge.py, README.md, docs/decisions/pr-review-record.md, docs/decisions/lanes-run-no-full-ci-job.md, docs/debts/notes.md, skills/ci-hygiene/SKILL.md, skills/project-ops/templates/brief.md and operating-model.md, bin/ci-job.
Left:
- A batch merges #1760. The branch is behind main, so it may need main merged in first.
- Two round-3 notes are sent to the coordinator to file in docs/debts/notes.md: (1) a repo whose checks job ci-job cannot read never gets a printed record; (2) "the tool gates printing" uses a verb the glossary bars.

