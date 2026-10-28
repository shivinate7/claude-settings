# c138-roadmap-precommit (cloud lane, Oct 28)

- c138: built and reviewed; branch `c138-roadmap-precommit` head 4c5b0b3 (on origin/roadmap 0e4e838, merges clean into e4761c7). Not on roadmap yet: the orchestrator lands it after telling triage.
- What it is: roadmap/hooks/pre-commit runs `build.py --check-staged`, which reads step files from the index and refuses a commit that adds or grows an open step's note past 250 words, naming it. Untouched over-cap notes, trims, done steps, deletions and a merge taking the other side's note pass. Setup, one line in CLAUDE.md: `git config core.hooksPath roadmap/hooks` (clone-wide).
- Tests: red first on a c122 note grown to 263 words; now 32 tests green (`python3 -m unittest roadmap.test_build`). build.py's own output and roadmap.html unchanged.
- Review: 2 Opus rounds. Round 1 fixed a done->open bypass, symlinked step files, a non-UTF-8 filename traceback, nested files, trims, a python fallback. Round 2: no blocking or should-fix; the one nit (a file named `.json`) fixed. No false alarm found on a commit build.py's cap accepts.
- Known, accepted: a clean merge or cherry-pick of a `--no-verify` commit is not checked (git runs no pre-commit there); a JSON-list note crashes but refuses (build.py crashes too); Python 2 as `python` gives a traceback. The task said not to run the red test on today's c122 append; history shows no c122 note over 250 (max 245), so the test uses a synthetic one.
- Once landed, triage: each existing clone/worktree needs the setup line run once.
