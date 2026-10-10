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

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). It LOGS.
- A builder's SubagentStop. It LOGS.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path.
  It DENIES.

## Verdict: the diff check logs, it does not block

Owner ruling, 2026-10-02. At commit, push and stop, an offence writes one `noted` line,
`builder-diff` or `author-diff`, with the path, and the guard allows the act. An unreadable diff
logs `role-diff-unread` at commit, push and stop. The reviewer reads the log and the diff.

Why: the base can be wrong, and a refusal on a wrong base is a false alarm, which spends the
guard (CLAUDE.md, verification-cry-wolf-guard-is-spent). The base is the OLDEST `HEAD` reflog
entry. A branch cut from a non-default branch counts that branch's files as the agent's own.
Unmeasured: how often it fired wrongly. The outcome protected, a green run that means that the code
is right, now rests on the reviewer and on the Edit/Write denial.

Trigger to restore blocking: fix the base bug. Then a refusal at commit, push and stop returns,
with the undo route and the once-only stop.

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

## Stops the guard cannot judge

A stop the guard cannot judge always logs. These are the logs: `role-diff-nocwd` (no cwd),
`role-diff-main-checkout` (the cwd is a main checkout, which holds no agent's own work), and
`role-diff-unread`. A second stop (`stop_hook_active`) with an offence logs
`role-diff-unresolved`.

## Roles

The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session
started with `--agent builder` (no `agent_id`) stay allowed.

- `builder` (diff rule `builder-diff`, write rule `builder-test-edit`): logged when the diff
  holds a test path. The write tool denies it.
- `test-author` (diff rule `author-diff`, write rule `test-author-scope`,
  `agents/test-author.md`): the inverse. Logged when the diff holds anything but a test path, test config, or a dev dependency list.
- `record-writer` (diff rule `writer-diff`, write rule `record-writer-scope`,
  `agents/record-writer.md`): logged when the diff holds anything but a `.md` file. The write tool
  denies it. The model ruling is in subagent-model-cap.

Each write refusal name no path. They say: report the needed change, and the orchestrator assigns it
to another role (rule git-remedy-never-names-target).

## Test path

A basename is `test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`,
`conftest.py`, `jest.setup.*`, or `*Test.java` (case matters, so `Contest.java` is not a test).
A directory part is `tests`, `test`, `__tests__`, `spec`, `testdata`, `__snapshots__`, or
`test_support`. Parts count from the nearest parent that holds `.git`. So a clone under a
folder named `tests` is not all test files.

Test config is `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `package.json`, and the
jest, vitest, playwright, karma, and mocha configs. If a builder change to such a file ADDS a
line that disables tests, it counts as a test change. Some names belong to test runners only,
such as `testpaths` and `testPathIgnorePatterns`. They count in any test config. A flag
(`--ignore`, `--deselect`) counts only in a test-runner context. That context is pytest
`addopts`, a `[tool.pytest*]` section, or a script line that calls pytest, jest, vitest,
mocha, or `go test`. So `ruff check --ignore E501` and `flake8 --ignore=E203` stay free.
Flags match exactly, so `--ignore-scripts` is no hit. A new dependency stays allowed.

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

## Threat model, and known gaps

The guard stops ACCIDENTAL test edits. It does not stop a deliberate evasion. The reviewer
reads every diff, so a deliberate test edit is caught there. These gaps are known and have no
new code:

- `git update-ref` or `git branch -f` can move a base.
- A new worktree can reset the reflog base.
- A commit made through `sh -c` or a subshell is not read at commit time. The stop check still
  reads the diff.
- The diff check does not block, so an agent can commit a test change. The reviewer must read
  the log.

Measured 2026-10-03, q_max: a test-author got an Edit refusal, then wrote the same file with
Bash and Python. The reviewer caught it. This is the first measured deliberate evasion. The
owner ruled prose only: `agents/builder.md` and `agents/test-author.md` say a refusal is final,
and an agent never writes a refused path another way. The diff check still logs and does not
block. Deferred item refusal-route-around-guard holds the forced-guard option for later.

## Known ceilings (bandaids, named)

- The SubagentStop `cwd` is read from the payload. It was not measured live.
- `spec` as a directory also covers design-spec folders. The brief chose this.
- Skip markers are read only in test config and test paths. A skip in product code skips no test.
- The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A
  test-author changes them.

## Test author

The orchestrator gives a test to a test-author, before or after the build. The builder reports
the test change it needs and never writes it (`agents/builder.md`).
