# Builders cannot edit tests

## Outcome protected

A builder that cannot pass a test must not delete, skip, or rewrite it. A green run must mean
that the code is right. ImpossibleBench (arXiv 2510.20270) measured it. Read-only tests block
direct test edits, with little loss of real performance.

## Judge the result, not the commands

The first version read shell commands: `rm`, `mv`, `sed -i`, a redirect. A review found a
bypass for each. The bypasses were `bash -c`, `find -delete`, `xargs rm`, `dd`, `rsync`,
`patch`, `git apply`, `cp -t`, a variable, a symlink into the test folder, and a PowerShell
backslash path. The commands are not the act. The act is a test path in the diff
(decisions/predicate-is-the-act.md). The owner ruled: check the diff, and delete the command
clauses.

`hooks/guard.py` reads one diff at three points:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell).
- A builder's SubagentStop. The guard answers `decision: block`. The agent must fix its tree.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path.

The diff is the working tree against the commit where the agent's branch started. That commit
is the first line of the branch reflog. The merge base with the default branch stands in when
the reflog is missing. Untracked files count. A change put back to the base bytes is no
change. Each path is read as spelled and as resolved through symlinks. Backslashes become `/`.

## Roles

The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session
started with `--agent builder` (no `agent_id`) stay allowed.

- `builder` (rule `builder-test-edit`): refused when the diff holds a test path.
- `test-author` (rule `test-author-scope`, `agents/test-author.md`): the inverse. Refused when
  the diff holds anything but a test path or test config.

Both reasons name no path. They say: undo the change, report the needed change, and the
orchestrator assigns it to the other role (rule git-remedy-never-names-target).

## Test path

A basename is `test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`, or
`conftest.py`. A directory part is `tests`, `test`, `__tests__`, or `spec`. Parts count from
the nearest parent that holds `.git`. So a clone under a folder named `tests` is not all test
files.

Test config is `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `package.json`, and the
jest, vitest, playwright, karma, and mocha configs. If a builder change to such a file ADDS a
line that disables tests, it counts as a test change. Examples are `--deselect`, `--ignore`,
`testpaths`, `collect_ignore`, `testPathIgnorePatterns`, and a skip or xfail marker. A new
dependency stays allowed. For a test-author, test config is always its own. The exception is
`package.json`, which also holds the product manifest.

## False alarms pinned (decisions/guard-that-cries-wolf-is-spent.md)

These stay allowed for a builder:

- A change to `src/contest.py`, `latest_results.md`, or `attest.md`.
- A rename or delete of product files.
- A dependency or a script added to a manifest.
- A symlink to product code, a clean tree, and reads of tests.
- Test changes that the branch inherited from its parent.

A tree that git cannot read is allowed. The guard logs it as `role-diff-unread`. It never
reads that as clear.

## Known ceilings (bandaids, named)

- A SubagentStop block repeats until the tree is clean. No loop cap was measured.
- The SubagentStop `cwd` is read from the payload. It was not measured live.
- `spec` as a directory also covers design-spec folders. The brief chose this.
- Skip markers are read only in test config and test paths. A skip in product code skips no test.
- The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A
  test-author changes them.

## Test author

The orchestrator gives a test to a test-author, before or after the build. The builder reports
the test change it needs and never writes it (`agents/builder.md`).
