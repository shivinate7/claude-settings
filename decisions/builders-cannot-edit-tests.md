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
- A builder's SubagentStop. The guard answers `decision: block`.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path.

## What counts as the agent's own change

The diff is the working tree against a base, plus untracked files. A change put back to the
base bytes is no change. Each path is read as spelled and as resolved through symlinks.
Backslashes become `/`. There are TWO bases, and a path counts only if it differs from both:

- The oldest `HEAD` reflog entry: the commit where the worktree was cut. A new branch name
  (`git switch -c b2`) does not move it. Work that the parent branch handed over does not
  differ from it.
- The merge base of `HEAD` with the default branch. It moves forward each time main is merged
  or rebased in. Work that main gained later does not differ from it.

Only the agent's own change differs from both.

## The stop gives up once

A refusal at SubagentStop blocks the stop once. A second stop (`stop_hook_active`) is allowed,
and the guard logs `role-diff-unresolved`. So an agent that cannot fix its tree never loops.
The reason names the undo route with placeholders and no target:
`git show <base>:<path> > <path>` restores a file, and `rm <path>` removes a new file.

A stop the guard cannot judge always logs. These are the logs: `role-diff-nocwd` (no cwd),
`role-diff-main-checkout` (the cwd is a main checkout, which holds no agent's own work), and
`role-diff-unread`. At SubagentStop an unread diff blocks once, under the same cap.

## Roles

The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session
started with `--agent builder` (no `agent_id`) stay allowed.

- `builder` (rule `builder-test-edit`): refused when the diff holds a test path.
- `test-author` (rule `test-author-scope`, `agents/test-author.md`): the inverse. Refused when
  the diff holds anything but a test path, test config, or a dev dependency list.

Both reasons name no path. They say: report the needed change, and the orchestrator assigns it
to the other role (rule git-remedy-never-names-target).

## Test path

A basename is `test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`,
`conftest.py`, `jest.setup.*`, or `*Test.java` (case matters, so `Contest.java` is not a test).
A directory part is `tests`, `test`, `__tests__`, `spec`, `testdata`, `__snapshots__`, or
`test_support`. Parts count from the nearest parent that holds `.git`. So a clone under a
folder named `tests` is not all test files.

Test config is `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `package.json`, and the
jest, vitest, playwright, karma, and mocha configs. If a builder change to such a file ADDS a
line that disables tests, it counts as a test change. The disabling flags match exactly, so
`--ignore-scripts` is no hit. A new dependency stays allowed.

For a test-author:

- Test config files are its own, except two.
- `package.json`: it may change `devDependencies`, `jest`, and the test scripts only.
- `pyproject.toml`: it may change the `[tool.pytest*]` sections only.
- `requirements-dev.txt` is its own. A builder may add a dev dependency.

## False alarms pinned (decisions/guard-that-cries-wolf-is-spent.md)

These stay allowed for a builder:

- A change to `src/contest.py`, `Contest.java`, `latest_results.md`, or `attest.md`.
- A rename or delete of product files.
- A dependency or a script added to a manifest, `--ignore-scripts` included.
- A symlink to product code, a clean tree, and reads of tests.
- Test changes that the branch inherited, or that main brought in a merge.

## Known ceilings (bandaids, named)

- The SubagentStop `cwd` is read from the payload. It was not measured live.
- `spec` as a directory also covers design-spec folders. The brief chose this.
- Skip markers are read only in test config and test paths. A skip in product code skips no test.
- The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A
  test-author changes them.

## Test author

The orchestrator gives a test to a test-author, before or after the build. The builder reports
the test change it needs and never writes it (`agents/builder.md`).
