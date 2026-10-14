# No case pins the heredoc bodies kept for ts-node and node.cmd

- **What.** The guard keeps the heredoc body under inspection for `ts-node -`, `babel-node -`, `git-bash.exe -c` and `node.cmd -`. A review confirmed this by a probe, but no test case covers these headers. Only the file-name case `node-notes.md` has cases. A later regex change can drop these bodies with no red test.
- **Where.** `INTERPRETER_HEREDOC` in `hooks/guard_core.py`; cases in the impeccable family of `hooks/test_guard.py`.
- **Decision.** `design-skills` (only a reviewer runs the impeccable skill).
- **Retire.** Add one case for each of the four headers with a body that runs the skill. Each case denies, and goes red when the regex drops the body.
