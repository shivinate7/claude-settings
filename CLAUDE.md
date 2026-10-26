# advisor repo: the roadmap record and briefs

This repo holds the record for the claude-settings project on claude.ai: the roadmap, briefs and
plans. That project's instructions govern how to work. This file holds the repo mechanics only.
No session runs from this folder: the terminal advisor retired on Oct 26 (owner, step c51).

- The roadmap is the record: roadmap/data/ (steps/, topics/, meta/, one JSON file each). Trust it
  over memory, and say when it and the repos disagree.
- After each edit to roadmap/data/: run `python roadmap/build.py`, commit the JSON and
  roadmap/roadmap.html, and push to main. Then republish roadmap/roadmap.html to the roadmap page,
  https://claude.ai/artifact/R3iCpK91QRjC5he8bwfY7m (Artifact tool, same URL). The page is
  read-only; it shows the record as of its last publish.
- Other threads edit this repo too. Pull right before each write. If roadmap.html conflicts on a
  pull, run build.py again rather than merging it by hand.
- Briefs go in briefs/, plans in plans/, hand-off notes in handoffs/. A brief's full text also
  goes in its step's ask field.
