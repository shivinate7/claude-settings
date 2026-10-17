# Builders cannot edit tests

## The ruling

A builder that cannot pass a test must not delete, skip or rewrite it. A green run must mean the code is right. Read-only tests block direct test edits with little loss of real performance (ImpossibleBench, arXiv 2510.20270).

Judge the result, not the commands. The act is a test path in the diff (`predicate-is-the-act`), not `rm`, `mv`, `sed -i` or a redirect, which each had a bypass. `hooks/guard.py` reads one diff at three points:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). It LOGS.
- A builder's SubagentStop. It LOGS.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path. It DENIES. Every path field the call carries is judged, and every deny runs on all fields before any ask, so a decoy field cannot hide a denied path.

Owner, 2026-10-02: at commit, push and stop, an offence writes one `noted` line (`builder-diff` or `author-diff`) with the path, and the guard allows the act. An unreadable diff logs `role-diff-unread`. The reviewer reads the log and the diff. Why: the base can be wrong, and a refusal on a wrong base is a false alarm (`verification-cry-wolf-guard-is-spent`). The outcome rests on the reviewer and on the Edit and Write denial. Restore blocking when the base bug is fixed, with the undo route and the once-only stop.

**What counts as the agent's own change.** The diff is the working tree against a base, plus untracked files. A change put back to the base bytes is no change. Each path is read as spelled and as resolved through symlinks. Backslashes become `/`. A path counts only if it differs from both bases:

- The oldest `HEAD` reflog entry: the commit where the worktree was cut. A new branch name does not move it.
- The merge base of `HEAD` with the default branch. It moves forward each time main is merged or rebased in.

**Stops the guard cannot judge** always log: `role-diff-nocwd` (no cwd), `role-diff-main-checkout` (the cwd is a main checkout), `role-diff-unread`. A second stop (`stop_hook_active`) with an offence logs `role-diff-unresolved`.

**Roles.** The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session started with `--agent builder` (no `agent_id`) stay allowed.

- `builder` (diff rule `builder-diff`, write rule `builder-test-edit`): logged when the diff holds a test path. The write tool denies it.
- `test-author` (`author-diff`, `test-author-scope`, `agents/test-author.md`): the inverse. Logged when the diff holds anything but a test path, test config or a dev dependency list.
- `record-writer` (`writer-diff`, `record-writer-scope`, `agents/record-writer.md`): logged when the diff holds anything but a `.md` file. The write tool denies it. The model ruling is in `subagent-model-cap`.
- Each write refusal names no path. It says to report the needed change, and the orchestrator assigns it to another role (`git-remedy-never-names-target`).
- The orchestrator gives a test to a test-author, before or after the build. The builder reports the test change it needs and never writes it (`agents/builder.md`).

**Test path.** A basename is `test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, `*.spec.*`, `conftest.py`, `jest.setup.*`, `*Test.java` or `<Name>Tests.swift`. Case matters, so `Contest.java` is not a test. Swift counts the plural only. A directory part is `tests`, `test`, `__tests__`, `spec`, `testdata`, `__snapshots__` or `test_support`. An Xcode or SwiftPM test target folder also counts: a PascalCase part ending in `Tests`, such as `DegenUITests`. Outside a git repo, every part of an absolute path counts. Parts count from the nearest parent that holds `.git`.

**Test config** is `pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `package.json`, an Xcode `.xctestplan`, and the jest, vitest, playwright, karma and mocha configs. A builder change to such a file that ADDS a line disabling tests counts as a test change. Names such as `testpaths` and `testPathIgnorePatterns` count in any test config. A flag (`--ignore`, `--deselect`) counts only in a test-runner context: pytest `addopts`, a `[tool.pytest*]` section, or a script line that calls pytest, jest, vitest, mocha or `go test`. So `ruff check --ignore E501` and `flake8 --ignore=E203` stay free. Flags match exactly, so `--ignore-scripts` is no hit. A new dependency stays allowed.

For a test-author: test config files are its own, except `package.json` (only `devDependencies`, `jest` and the test scripts) and `pyproject.toml` (only the `[tool.pytest*]` sections). `requirements-dev.txt` is its own. A builder may add a dev dependency.

**False alarms pinned** (`guard-that-cries-wolf-is-spent`), allowed for a builder: a change to `src/contest.py`, `Contest.java`, `latest_results.md` or `attest.md`. A rename or delete of product files. A dependency or a script added to a manifest. A symlink to product code, a clean tree, and reads of tests. Test changes the branch inherited, or that main brought in a merge.

## Limits

The guard stops ACCIDENTAL test edits (`guard-guards-mistakes-only`). The reviewer reads every diff. Known gaps with no new code:

- `git update-ref` or `git branch -f` can move a base. A new worktree can reset the reflog base.
- A commit made through `sh -c` or a subshell is not read at commit time. The stop check still reads the diff.
- The diff check does not block, so an agent can commit a test change. The reviewer must read the log.
- A file hard-linked to a file in another checkout passes the write deny.
- A product folder named like `ABTests` reads as a test folder. `FooSpec.swift` (Quick) and Objective-C `FooTests.m` are not seen.
- In a `.xctestplan`, only `skippedTests` counts as disabling tests. `selectedTests`, `"enabled" : false` and a `.xcscheme` `<SkippedTests>` are not read.
- `spec` as a directory also covers design-spec folders. Skip markers are read only in test config and test paths.
- The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A test-author changes them.
- The SubagentStop `cwd` is read from the payload, not measured live.
- A test-author that got an Edit refusal wrote the same file with Bash and Python. The reviewer caught it. Prose only (owner): `agents/builder.md` and `agents/test-author.md` say a refusal is final and an agent never writes a refused path another way. Deferred item `refusal-route-around-guard` holds the forced-guard option.

Kind: process
Home: hooks/guard.py
