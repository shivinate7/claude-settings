# Handoff: lane mockup-homes

Written 2026-11-02 12:40 CST at the owner's wind-down (12:31 CST). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe.

## Goal

Mockups survive a Claude account switch on one Mac. Owner ask 11:49 CST Nov 2. Incident: the mockups for home
waiting items 48 and 49 lived only in `~/Library/Application Support/Claude-Work/side-session-notes/<session id>/`.

1. A mockup has a machine home outside any session: `~/Developer/<repo>-imports/<item>/`, or the repo's design
   folder (`docs/design`) when kept. The waiting-page guard refuses a design whose `file` is not under a home.
2. A mockup id (`item<N>-<letter>`) in a roadmap step carries its path in the step field `mockups: {id: path}`.
   The roadmap build fails an id with no file behind it.

## Rulings

- Lane, 12:06 CST: a machine-home path from another machine (Windows form read by a Linux cloud build), or a home
  whose `<repo>-imports` folder is absent, reads unknown in the roadmap build (`mockup file unread: ...`, exit 0),
  never a miss. The waiting-page guard judges against this machine's home.
- Departs from main: adds a required `file` on each design. Sent to the coordinator 11:58 CST, not blocking.

## State

- Branch `mockup-homes` on origin. Code head f2caab9f, base 74be1279. No PR opened yet.
- Built (builder sonnet): `lint/layout.py` (`mockup_homes`, `mockup_home_problem`, one constant pair),
  `hooks/question_form.py` (`design_file_problems`), `hooks/guard.py` (rule `mockup-home`, before
  `page_design_hit`), `skills/roadmap/build.py` (`mockups` field, miss line, exit 1),
  `docs/decisions/mockup-home.md`, `skills/roadmap/SKILL.md`, `skills/waiting-page/SKILL.md` ("Add a design" step 4 only).
- Tests (test-author): red on 74be1279 shown. Now green: `lint/test_layout.py`, `GUARD_FAMILY=page-item-design
  hooks/test_guard.py`, `ci-job checks --lint`, `check_silent_undo --strict`.
- Red, 1 case: `skills/roadmap/test_build.py` `MockupFiles.test_a_cite_inside_a_longer_token_is_not_a_mockup_id`.
  It uses `item480-a`, which is a valid id. The test is wrong: replace it with a true lookalike such as `1item48-a`.
- Not reviewed. No review round has run.

## Next

1. Test-author: fix the `item480-a` case; add two ruling cases in `MockupFiles`: a Windows-form path in a Linux
   build reads unknown (exit 0, `mockup file unread: c1 item48-a`); a Windows `AppData\...\side-session-notes\...`
   path is still a miss (exit 1).
2. Run `hooks/mutate_guard.py` once for rule `mockup-home`.
3. Reviewer (round 1). This changes a guard, so the review-cap rules apply.
4. Draft PR; send its number, head and verdict to batch runner 7 (session_013NEJKyjt96cx7d1uCdtb8U) and the
   coordinator. `docs/records.md` row comes from `python3 lint/hook_catalog.py --root .` at merge.
5. Merge origin/main before hand-off: lane waiting-data-in-repo also edits `skills/waiting-page/SKILL.md`.

## Open questions

- The roadmap build checks steps of every status, so a done step that cites an id with no `mockups` entry keeps
  the build red. Skip done steps? Owner: coordinator to bring to the owner. Lane leans: check open steps only.

## Left unpushed

Nothing. Worktrees `.claude/worktrees/agent-ac69686331afe12e3` (branch `mockup-homes-tests`, b4ce48e0, contained in
`mockup-homes`) and `.claude/worktrees/agent-a2dcd3c589a075397` are clean.
