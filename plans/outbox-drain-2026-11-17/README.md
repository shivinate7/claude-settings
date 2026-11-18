# Outbox drain sort, roadmap/outbox/triage.md, Nov 17 2026

Step: triage-outbox-drain. Six read-only Explore sorters (sonnet), 22:09 to 22:27 CST, each sorted every bullet of one line range of roadmap/outbox/triage.md against origin/main b58eb9848. Triage 11 wrote this folder; nothing in triage.md is moved or deleted.

Totals over 1,900 bullets: K 480 (finding true, not on main), F 308 (filed), S 675 (stale), J 361 (journal line on an open step), R 25 (owner words no ruling holds), U 51 (unsure).

Files: sort-1.md lines 1-340, sort-2.md 341-680, sort-3.md 681-1020, sort-4.md 1021-1360, sort-5.md 1361-1700, sort-6.md 1701-1999. Each lists line numbers per class and what the sorter did not check.

Known limits (each report states them): PR merged or closed state came from main commit subjects, not GitHub; K rests on one grep per bullet; F is an upper bound; J may hide F; the step data the sorters read may lag origin/roadmap.

Acts that follow, none done yet:
- K: one-line notes on main, in the form at triage.md line 5, after draft PR 3569 (one file per note) merges.
- J: append to the named open step's note, by slug.
- S: drop from triage.md once K is filed.
- R: file rulings only from owner words that no ruling holds; the owner's answers are in waiting/answers/*.json.
- U: re-read one by one.
