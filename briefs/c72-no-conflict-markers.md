# c72: a roadmap write never lands with git conflict markers in it

Cloud build thread brief. Build advisor (4), Oct 26. Branch: roadmap (direct push, no PR, never
merged into main). Pull right before each write. Only Triage the roadmap (3) republishes the page.

## Incident

Oct 26 16:34, roadmap 45891d5: steps/o13.json and roadmap.html were pushed with conflict markers.
The writer committed mid-rebase after build.py crashed on the bad JSON; the shell chain used `;`,
so the crash did not stop the commit. Fixed at 6927b4c.

## Task

1. roadmap/build.py: before it builds, scan every tracked text file under roadmap/, briefs/,
   plans/ and handoffs/ for a line that starts with `<<<<<<< `, `=======` alone, or `>>>>>>> `.
   On a hit, print each file and line and exit non-zero, and write no page. A `=======` line inside
   a Markdown file is a setext heading only when the line above has text and no `<<<<<<<` precedes
   it: flag `=======` only between a `<<<<<<<` and a `>>>>>>>`.
2. roadmap/README.md: the write recipe chains with `&&` (build, then add, commit, pull --rebase,
   build again, push), and says to stop on a failed rebase, never commit during one.
3. A small test file beside build.py: a planted marker in a step file fails; a planted one in a
   brief fails; a Markdown setext `=======` heading passes (false alarm); the clean tree passes.
   Show it red before the build.py change.

Cost: one read of each file per build, no file written. Port to other repos: yes (triage's call):
o16 packages build.py with the roadmap.

## Report

Cap 10 lines: Done, Deviations, Next, Port line. A fresh Sonnet reviewer reads the diff (it adds a
check). Report to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT).
