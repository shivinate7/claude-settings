# Builders cannot edit tests

## The ruling

A builder that cannot pass a test must not delete, skip or rewrite it. A green run must mean the code is right. The guard stops mistakes, not an attacker (`guard-guards-mistakes-only`). The reviewer reads every diff.

Judge the result, not the commands. The act is a test path in the diff (`predicate-is-the-act`), not `rm`, `mv`, `sed -i` or a redirect. `hooks/guard.py` reads one diff at three points:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). A test change refuses with `builder-diff`. The refusal names no path and gives the undo route. No override lifts it.
- A builder's SubagentStop. A test change blocks the first stop with `builder-diff`. A second stop (`stop_hook_active`) is allowed and logs `role-diff-unresolved`, so an agent that cannot fix its tree never loops.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path. It refuses. Every path field the call carries is judged, and every refusal runs on all fields before any ask, so a decoy field cannot hide a refused path.

An unreadable diff logs `role-diff-unread` and is allowed. A second stop with an unreadable diff logs `role-diff-unresolved`.

**Ruling.** Coordinator, 2026-11-01 20:32 CST, restored the refusal. The Oct 2 owner ruling set its condition: the base defect is fixed. The base rule below is that fix. Incident 95b4348b (lane page-item-checked-at-write, 2026-11-01) is pinned by the first `builder-refuse` case.

## The base rule

The diff is judged against bases. A wrong base made a refusal a false alarm, and a false alarm spends the guard (`verification-cry-wolf-guard-is-spent`). A base is a commit the agent received. Read them from the HEAD reflog. Those are the start commit, each reset, checkout, pull, fast-forward or clean merge target, and rebase start. Add each merged-in parent of a merge commit, and the merge base with the default branch. Only independent tips count. A base that another base descends from does not count.

- A base that holds the agent's own commits is set aside only for the paths those commits touched.
- A path offends only if it differs from every independent tip that vouches for it.
- A test path that both sides changed in a merge the builder committed by hand offends. Resolving that conflict chooses what the test checks.
- The deny names the independent tip shas that judged the path, 12 characters each, and no path.

**Cost.** Git reads only. No timer and no long-lived process. Each commit, push and stop costs one reflog read and one merge base with the default branch. Per base it costs about two reads (tracked diff, untracked list), and one rev-list when the agent has own commits. Per own commit it costs one diff-tree. Per hand merge it costs a few reads. A log line is written only for an offence or an unread diff.

**Measure.** `GUARD_FAMILY=builder-refuse hooks/test_guard.py`: all 37 `builder-refuse` cases pass on this tip. The coordinator measured 25 of 25 `role-diff` mutants killed (`hooks/mutate_guard.py`) before three more were added. Those three are unmeasured.

## Roles

The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session started with `--agent builder` (no `agent_id`) stay allowed.

- `builder`: refused at commit, push and stop when the diff holds a test path. The write tool refuses it too.
- `test-author`: the inverse. Logged when the diff holds anything but a test path, test config or a dev dependency list (`author-diff`). Never refused at commit, push or stop.
- `record-writer`: may change only `*.md` files: records, README, CLAUDE.md-style docs, agent files, skills and output styles. It never changes product code, tests, CI or config. The write tool refuses any other path (`record-writer-scope`). At commit, push and stop, a diff that holds one is logged only (`writer-diff`).
  - Reason: a role name is only a label on the spawn. With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and the floor means nothing (`agent-model-cap`).
- `designer`: at commit, push and stop, an offence is logged only (`designer-diff`).
- Each write refusal names no path. It says to report the needed change, and the orchestrator assigns it to another role (`git-remedy-never-names-target`).
- The orchestrator gives a test to a test-author, before or after the build. The builder reports the test change it needs and never writes it (`agents/builder.md`).
- A refusal is final: an agent never writes a refused path another way. The write tool refuses by path. At commit, push and stop, a builder's test change is judged on the whole diff, so a test file written by shell is refused there too. Other refused paths rest on prose only (owner), in `agents/builder.md` and `agents/test-author.md`.

**Test paths and test config.** The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A test-author changes them.

- A builder change to a test-runner config file that ADDS a line disabling tests counts as a test change.
- A test-author owns test config files and `requirements-dev.txt`. Two files are partly owned: `package.json` (only `devDependencies`, `jest` and the test scripts) and `pyproject.toml` (only the `[tool.pytest*]` sections).
- A builder may add a dependency or a dev dependency.

**False alarms pinned** (`guard-that-cries-wolf-is-spent`). A builder may still do these:

- Rename or delete product files, and add a dependency or a script to a manifest.
- Read tests, and keep test changes that the branch inherited or that main brought in a merge. Keeping them needs no edit. A merge conflict in a test file is not the builder's to resolve: resolving it chooses what the test checks, so a test-author resolves it. The refusal says so.
- Use a name that only looks like a test, such as `src/contest.py`.

Kind: process
Home: hooks/guard.py
