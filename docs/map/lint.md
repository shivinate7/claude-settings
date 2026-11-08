# Lint

The checks and tools under `lint/`. The pilot map covers two files here.

## Code files

- `lint/find_copies.py` — Lists the copies that a child repo holds of claude-settings files and skills. It only reads, and it never fixes a copy.
  - A near-equal file needs 12 significant lines on the parent side. — `MIN_LINES = 12`
  - A child file with over 2 times the parent's lines only quotes it, so it is no copy. — `CHILD_GROWTH = 2`
  - A parent file under examples or templates is meant to be copied, so it is never a copy. — `TEMPLATE_DIRS = {"examples", "templates"}`
  - It starts git with no console window, through the one home. — `uses hooks/_nowindow.py:run`
- `lint/check_cost_pins.py` — Refuses a decision record's Cost sentence that names a file when no test in that sentence holds the file's whole name. It reads the records, each test file a Cost sentence names (once per run), and `lint/layout.json` through `lint/layout.py`, and it never fixes a record. It misses a file with an unlisted extension, a path with no extension, and a name outside backticks. It also misses a Cost paragraph that only a table row or an underlined heading would open. It also refuses a count of work in a Cost sentence when the sentence has no bound, no mark, and no nearest code span that a test holds as a whole name.
  - Tested by: `lint/test_check_cost_pins.py`
