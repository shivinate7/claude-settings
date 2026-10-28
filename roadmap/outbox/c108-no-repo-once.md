# c108-no-repo-once

- c108, decision watch says once per session when a folder has no git repo: built and reviewed. Draft PR #734 (c108: no-repo line once per session), head 554bab4. The builder (opus) showed it red, then green. Reviewer (opus), round 1: clear. Local gates: 58 of 61 suites pass, ste-changed passes. test_guard (load-brake child count) and test_handoff_wave2 (root can delete the pointer) fail; a run on main to check whether they are environmental is in progress.
- c108 reviewer notes, not debts (rare in normal work):
  - A folder with no `.git`, using GIT_DIR or GIT_WORK_TREE from the environment, is now told "not a git repo" once and is then silent. Main said UNKNOWN on every turn there. Possible fix: count GIT_DIR in the environment as a repo.
  - `is_git_work_tree` uses `os.path.exists`, so a parent folder that cannot be read reads as "not a repo". Possible fix: use lstat and count any error other than not-found as a repo.
  - The flag is once per session, not once per folder. That matches the ruling.
