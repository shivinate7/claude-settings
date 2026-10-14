# The import and export comment is stale

- **What.** The comment above the import and export rows in `hooks/test_guard.py` says `import` and `export` are not git subcommands. Git 2.55 lists both in `git stash -h`, and the guard's own docstring says so.
- **Where.** `hooks/test_guard.py`, the comment above the import and export rows. Line 1602 at this commit.
- **Decision.** `stash-stack-is-a-shared-subject`: `export` and `import` are known action words and keep the stack side.
- **Retire.** The comment states what git 2.55 lists. A check: no line in `hooks/test_guard.py` says those words are not git subcommands. The edit is in a test file, so a test-author lane makes it.
