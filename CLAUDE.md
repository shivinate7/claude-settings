# claude-settings, branch `roadmap`: the roadmap record and briefs

This branch holds the record for the claude-settings project on claude.ai: the roadmap, briefs,
plans and hand-off notes. It shares no history with main, needs no PR, and runs no CI. Never merge
it into main. The project's instructions govern how to work; this file holds the mechanics only.
It moved here from shivinate7/advisor on Oct 26 (owner, step c51), with that repo's history.

- The roadmap is the record: roadmap/data/ (steps/, topics/, meta/, one JSON file each). Trust it
  over memory, and say when it and the repos disagree.
- To file: `git fetch origin roadmap`, work on a checkout of `roadmap` (a worktree is fine), edit,
  run `python roadmap/build.py`, commit the JSON and roadmap/roadmap.html, `git push origin roadmap`.
  Then the waiting-page writer (triage) splices the roadmap block into the waiting page's Status tab (title '<repo> Queue'),
  https://claude.ai/artifact/RddcgXbB6SvTrFZHPmsvFx (skill waiting-page, "Update the roadmap block").
  The old roadmap page gets no more publishes (skill roadmap, main).
- Once per clone, run `sh roadmap/hooks/install.sh` (never set core.hooksPath): its pre-commit refuses a
  commit that adds or grows an open step's note past 250 words in a roadmap checkout (build.py
  `--check-staged`, step c138), and is a no-op elsewhere. It leaves other hooks (main-ref) in place and
  chains a pre-commit already there.
- Other threads file here too. Pull right before each write. If roadmap.html conflicts on a pull,
  run build.py again rather than merging it by hand.
- Briefs go in briefs/, plans in plans/, hand-off notes in handoffs/. A brief's full text also
  goes in its step's ask field.

## Standing sessions

A lane brief names a standing session by role or lane slug, never by session id (owner 00:19 CST Nov 14, item 819 b; ruling R22 point 3). The lane looks the id up here. Triage rewrites a line when a role changes hands.

- Coordinator: "Claude settings coordinator onboarding", session_013NEJL1gw6EdrSyvHkTUEx6, since 2026-11-11 22:38 CST.
- Triage: "cs triage: claude-settings (7)", session_013NEJKzCzoWhfP8FMCPtQU6, since 2026-11-11 22:38 CST.
- Batch runner: "claude-settings batch runner 10", session_013NEJL2f1YCYsvLdpFqtWP3, since 2026-11-11 22:38 CST.
- Batch runner, child repos: "batch runner 11 (child repos)", session_013NEJKzRugXqBZrZ8xwXmW7, since 2026-11-11 22:46 CST; scope every child repo under shivinate7 and ssemwal-cdc, degen included (owner 11:13 CST Nov 13, item 704 b: "they're all children of claude-settings"; degen added 11:19 CST: "it can take degen too"); it fast-forwards each repo before every batch.
