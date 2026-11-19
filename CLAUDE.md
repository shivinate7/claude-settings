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
  `--check-staged`, step c138), or stages a step `updatedAt` or ruling `at` later than the clock
  (step updatedat-not-future), and is a no-op elsewhere. It leaves other hooks (main-ref) in place and
  chains a pre-commit already there.
- Other threads file here too. Pull right before each write. If roadmap.html conflicts on a pull,
  run build.py again rather than merging it by hand.
- Briefs go in briefs/, plans in plans/, hand-off notes in handoffs/. A brief's full text also
  goes in its step's ask field.

## Standing sessions

A lane brief names a standing session by role or lane slug, never by session id (owner 00:19 CST Nov 14, item 819 b; ruling R22 point 3). The lane looks the id up here. Triage rewrites a line when a role changes hands.

- A standing session reads any child repo itself: call `mcp__claude-code-remote__add_repo` with owner, repo and access `read` (measured 13:27 CST Nov 17 by triage 11: it attached the private repos home, degen, q_max, ios-adblock and joyous, and the GitHub MCP then read their PRs). A public repo (banchi, mailaudit) attached with `read` gives the session nothing and the guard's gh cannot read it; use access `push` there (coordinator, measured 11:4x CST Nov 17). Never write "no access to repo X" or report a merge there as unread before trying `add_repo` (owner 13:2x CST Nov 17, relayed in chat; step standing-sessions-add-repo).

- Coordinator: "Claude settings coordinator onboarding", session_013NEJL1gw6EdrSyvHkTUEx6, since 2026-11-11 22:38 CST.
- Triage: "cs triage: claude-settings (12)", session_013NEJL4EXwXj25GNvtH3U9g, since 2026-11-18 21:28 CST (triage 11, session_013NEJKzyLYRTQKeLpis8JKJ, archived at the owner's request, 21:2x CST Nov 18; roster row rewritten 22:56 CST at the consultant's ask).
- Consultant: session_013NEJKz5AWFJhGvmCUoi6wQ, the owner's voice (ruling own-consultant-speaks-for-owner, 20:24 CST Nov 14).
- Batch runner: "claude-settings batch runner 10", session_013NEJL2f1YCYsvLdpFqtWP3, since 2026-11-11 22:38 CST.
- Batch runner, child repos: "batch runner 11 (child repos)", session_013NEJKzRugXqBZrZ8xwXmW7, since 2026-11-11 22:46 CST; scope every child repo under shivinate7 and ssemwal-cdc, degen included (owner 11:13 CST Nov 13, item 704 b: "they're all children of claude-settings"; degen added 11:19 CST: "it can take degen too"); it fast-forwards each repo before every batch. Narrowed 00:26 CST Nov 14 (coordinator, relayed; consultant's ask 00:25): runner 11 keeps degen and home; batch runner 12 takes the other five. Degen scope narrowed 16:30 CST Nov 14 (owner, ruling own-841-degen-coordinator-spawned-only): only the degen PRs this account's coordinator spawned lanes for; degen drafts made by other sessions are out of scope.
- Batch runner, child repos q_max, banchi, mailaudit, ios-adblock and joyous: "batch runner 12", session_013NEJL33U96UiyE6UtCHct3, since 00:26 CST Nov 14 (coordinator, relayed); merges each lane's own PR on its own green run there (owner 00:19 CST Nov 14, item 820 c).
