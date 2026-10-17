# The records-page guard reads an exclude pathspec as naming the page

- **What.** `_names_page` returns True for each pathspec that starts with `:`. So `git add -A ':!docs/records.md'`, which leaves the page out, counts as an add that reaches the page. A later `git commit` then reads the working-tree page. If that page differs from HEAD's, the base's and origin's page, the commit is denied, but the add left the page out. This is a likely false alarm, found by reading the code. It is unrun.
- **Where.** `hooks/guard_merge.py`: `_names_page` (the `spec.startswith(":")` test) and `_add_shape`.
- **Decision.** `records-index-at-merge` (one records index page, rebuilt at merge time). Its "Holes, named" section names this gap.
- **Retire.** First run the case, to show the alarm is real. Then `_names_page` and `_add_shape` read `:!`, `:^` and `:(exclude)` specs as leaving that path out. A case in `hooks/test_guard.py`: `add -A ':!docs/records.md'`, then a commit with a changed working-tree page, is allowed. It shows red on the current code and green after the fix. The same call with a plain `add -A` stays denied.
