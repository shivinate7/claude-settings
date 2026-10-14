# The installer's worktree check has small gaps

- **What.** Four gaps, found in review:
  - An empty `catch` in `install.ps1` passes the no-git case, but it also hides any other error from the check.
  - The refusal says "the main clone" but does not print its path.
  - A folder with no `.git` that sits inside a worktree is refused, but the comment says it passes.
  - No test covers a piped install, a subfolder as the current folder, `GIT_DIR` in the environment, a path with spaces, or a symlink.
- **Where.** `install.ps1`, lines 18-29; `install.sh`, lines 107-108 and 168; `hooks/test_install_src.sh`; `install.test.ps1`.
- **Decision.** None. The incident of 2026-10-14 16:40 CDT: an install from a linked worktree pointed the owner's config at that worktree.
- **Retire.** The catch logs one line. The refusal prints the main clone path. The comment matches the code. Each listed shape has a test.
