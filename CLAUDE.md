# claude-settings, branch `roadmap`: the roadmap record and briefs

This branch holds the record for the claude-settings project on claude.ai: the roadmap, briefs,
plans and hand-off notes. It shares no history with main, needs no PR, and runs no CI. Never merge
it into main. The project's instructions govern how to work; this file holds the mechanics only.
It moved here from shivinate7/advisor on Oct 26 (owner, step c51), with that repo's history.

- The roadmap is the record: roadmap/data/ (steps/, topics/, meta/, one JSON file each). Trust it
  over memory, and say when it and the repos disagree.
- To file: `git fetch origin roadmap`, work on a checkout of `roadmap` (a worktree is fine), edit,
  run `python roadmap/build.py`, commit the JSON and roadmap/roadmap.html, `git push origin roadmap`.
  Then republish roadmap/roadmap.html to the roadmap page,
  https://claude.ai/artifact/JGqfvgXBuLqWUm1CX6Bv5h (Artifact tool, same URL).
- Once per clone, run `sh roadmap/hooks/install.sh` (never set core.hooksPath): its pre-commit refuses a
  commit that adds or grows an open step's note past 250 words in a roadmap checkout (build.py
  `--check-staged`, step c138), and is a no-op elsewhere. It leaves other hooks (main-ref) in place and
  chains a pre-commit already there.
- Other threads file here too. Pull right before each write. If roadmap.html conflicts on a pull,
  run build.py again rather than merging it by hand.
- Briefs go in briefs/, plans in plans/, hand-off notes in handoffs/. A brief's full text also
  goes in its step's ask field.
