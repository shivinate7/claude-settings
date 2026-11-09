# Lint

The checks and tools under `lint/`. The pilot map covers two files here.

## Code files

- `lint/find_copies.py` — Lists the copies that a child repo holds of claude-settings files and skills. It only reads, and it never fixes a copy.
  - A near-equal file needs 12 significant lines on the parent side. — `MIN_LINES = 12`
  - A child file with over 2 times the parent's lines only quotes it, so it is no copy. — `CHILD_GROWTH = 2`
  - A parent file under examples or templates is meant to be copied, so it is never a copy. — `TEMPLATE_DIRS = {"examples", "templates"}`
  - It starts git with no console window, through the one home. — `uses hooks/_nowindow.py:run`
- `lint/check_hook_output_pins.py` — Fails when a test file holds a literal copy of a line that a hook names in its `PRINTED_LINES`. It only reads, and it starts no process.
  - A printed text under 8 characters is ignored, since it would match too much. — `MIN_LENGTH = 8`
