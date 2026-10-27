# Builders cannot edit tests

## The ruling

A builder that cannot pass a test must not delete, skip or rewrite it. A green run must mean the code is right. The guard stops ACCIDENTAL test edits (`guard-guards-mistakes-only`). The reviewer reads every diff.

Judge the result, not the commands. The act is a test path in the diff (`predicate-is-the-act`), not `rm`, `mv`, `sed -i` or a redirect, which each had a bypass. `hooks/guard.py` reads one diff at three points:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). It LOGS.
- A builder's SubagentStop. It LOGS.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path. It DENIES. Every path field the call carries is judged, and every refusal runs on all fields before any ask, so a decoy field cannot hide a refused path.

Owner, 2026-10-02: at commit, push and stop, an offence writes one `noted` line (`builder-diff` or `author-diff`) with the path, and the guard allows the act. An unreadable diff logs `role-diff-unread`. The reviewer reads the log and the diff. Reason: the base can be wrong, and a refusal on a wrong base is a false alarm (`verification-cry-wolf-guard-is-spent`). Restore the refusal when the base defect is fixed, with the undo route and the once-only stop.

**Roles.** The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session started with `--agent builder` (no `agent_id`) stay allowed.

- `builder`: logged when the diff holds a test path. The write tool refuses it.
- `test-author`: the inverse. Logged when the diff holds anything but a test path, test config or a dev dependency list.
- `record-writer`: may change only `*.md` files: records, README, CLAUDE.md-style docs, agent files, skills and output styles. It never changes product code, tests, CI or config. The write tool refuses any other path (`record-writer-scope`). A diff that holds one is logged at commit, push or stop (`writer-diff`).
  - Reason: a role name is only a label on the spawn. With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and the floor means nothing (`agent-model-cap`).
- Each write refusal names no path. It says to report the needed change, and the orchestrator assigns it to another role (`git-remedy-never-names-target`).
- The orchestrator gives a test to a test-author, before or after the build. The builder reports the test change it needs and never writes it (`agents/builder.md`).
- A refusal is final: an agent never writes a refused path another way. This is prose only (owner), in `agents/builder.md` and `agents/test-author.md`. Debt `refusal-route-around-guard` holds the forced-guard option.

**Test paths and test config.** The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A test-author changes them.

- A builder change to a test-runner config file that ADDS a line disabling tests counts as a test change.
- A test-author owns test config files and `requirements-dev.txt`. Two files are partly owned: `package.json` (only `devDependencies`, `jest` and the test scripts) and `pyproject.toml` (only the `[tool.pytest*]` sections).
- A builder may add a dependency or a dev dependency.

**False alarms pinned** (`guard-that-cries-wolf-is-spent`). A builder may still do these:

- Rename or delete product files, and add a dependency or a script to a manifest.
- Read tests, and keep test changes that the branch inherited or that main brought in a merge.
- Use a name that only looks like a test, such as `src/contest.py`.

Kind: process
Home: hooks/guard.py
