# Builders cannot edit tests

## The ruling

A builder that cannot pass a test must not delete, skip or rewrite it. A green run must mean the code is right. Read-only tests block direct test edits with little loss of real performance (ImpossibleBench, arXiv 2510.20270).

Judge the result, not the commands. The act is a test path in the diff (`predicate-is-the-act`), not `rm`, `mv`, `sed -i` or a redirect, which each had a bypass. `hooks/guard.py` reads one diff at three points:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). It LOGS.
- A builder's SubagentStop. It LOGS.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path. It DENIES. Every path field the call carries is judged, and every deny runs on all fields before any ask, so a decoy field cannot hide a denied path.

Owner, 2026-10-02: at commit, push and stop, an offence writes one `noted` line (`builder-diff` or `author-diff`) with the path, and the guard allows the act. An unreadable diff logs `role-diff-unread`. The reviewer reads the log and the diff. Why: the base can be wrong, and a refusal on a wrong base is a false alarm (`verification-cry-wolf-guard-is-spent`). The outcome rests on the reviewer and on the Edit and Write denial. Restore blocking when the base bug is fixed, with the undo route and the once-only stop.

The guard stops ACCIDENTAL test edits (`guard-guards-mistakes-only`). The reviewer reads every diff.

**What counts as the agent's own change.** The diff is the working tree against a base, plus untracked files. A change put back to the base bytes is no change. Each path is read as spelled and as resolved through symlinks. A path counts only if it differs from both bases:

- The oldest `HEAD` reflog entry: the commit where the worktree was cut. A new branch name does not move it.
- The merge base of `HEAD` with the default branch. It moves forward each time main is merged or rebased in.

**Stops the guard cannot judge** always log: `role-diff-nocwd` (no cwd), `role-diff-main-checkout` (the cwd is a main checkout), `role-diff-unread`. A second stop (`stop_hook_active`) with an offence logs `role-diff-unresolved`.

**Roles.** The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session started with `--agent builder` (no `agent_id`) stay allowed.

- `builder` (diff rule `builder-diff`, write rule `builder-test-edit`): logged when the diff holds a test path. The write tool denies it.
- `test-author` (`author-diff`, `test-author-scope`, `agents/test-author.md`): the inverse. Logged when the diff holds anything but a test path, test config or a dev dependency list.
- `record-writer` (`writer-diff`, `record-writer-scope`, `agents/record-writer.md`): logged when the diff holds anything but a `.md` file. The write tool denies it. The model ruling is in `subagent-model-cap`.
- Each write refusal names no path. It says to report the needed change, and the orchestrator assigns it to another role (`git-remedy-never-names-target`).
- The orchestrator gives a test to a test-author, before or after the build. The builder reports the test change it needs and never writes it (`agents/builder.md`).
- A refusal is final: an agent never writes a refused path another way. This is prose only (owner), in `agents/builder.md` and `agents/test-author.md`. Deferred item `refusal-route-around-guard` holds the forced-guard option.

**Test path.** A basename in a common test naming form (`test_*.py`, `*.test.ts`, `*.spec.*`, `conftest.py`, `*Test.java`, `<Name>Tests.swift` and the like). Or a directory part such as `tests`, `__tests__`, `spec`, `testdata`, or an Xcode or SwiftPM test target folder. Case matters, so `Contest.java` is not a test. The list lives in `hooks/guard.py`. The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A test-author changes them.

**Test config** is the test-runner and package config (`pytest.ini`, `tox.ini`, `setup.cfg`, `pyproject.toml`, `package.json`, `.xctestplan`, and the jest, vitest, playwright, karma and mocha configs). A builder change to such a file that ADDS a line disabling tests counts as a test change. A flag such as `--ignore` counts only in a test-runner context, so `ruff check --ignore E501` stays free. A new dependency stays allowed.

For a test-author: test config files are its own, except `package.json` (only `devDependencies`, `jest` and the test scripts) and `pyproject.toml` (only the `[tool.pytest*]` sections). `requirements-dev.txt` is its own. A builder may add a dev dependency.

**False alarms pinned** (`guard-that-cries-wolf-is-spent`). These stay allowed for a builder:

- A name that only looks like a test, such as `src/contest.py` or `attest.md`.
- A rename or delete of product files, a dependency or a script added to a manifest, and a symlink to product code.
- Reads of tests, and test changes the branch inherited or that main brought in a merge.

Kind: process
Home: hooks/guard.py
