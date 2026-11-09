# Builders cannot edit tests

## The ruling

A builder that cannot pass a test must not delete, skip or rewrite it. A green run must mean the code is right. The guard stops mistakes, not an attacker (`guard-guards-mistakes-only`). The reviewer reads every diff.

Judge the result, not the commands. The act is a test path in a change the builder made (`predicate-is-the-act`), not `rm`, `mv`, `sed -i` or a redirect. `hooks/guard.py` reads that change at three points. A fourth point reads a builder's shell command, as an early warning:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). A test change refuses with `builder-diff`. The refusal names no path and gives the undo route: restore a changed test file, delete a new one. No override lifts it.
- A builder's SubagentStop. A test change refuses the first stop with `builder-diff`. A second stop (`stop_hook_active`) is allowed and logs `role-diff-unresolved`, so an agent that cannot fix its tree never loops.
- A write tool call (Edit, Write, MultiEdit, NotebookEdit). This is the early warning, by path. It refuses. Every path field the call carries is judged, and every refusal runs on all fields before any ask, so a decoy field cannot hide a refused path.
- A builder's Bash or PowerShell call that writes a test path. It refuses with `builder-test-edit`, the same reason as the write tool. The shell check below says what it reads.

An unreadable state logs `role-diff-unread` and is allowed. A second stop with an unreadable state logs `role-diff-unresolved`.

**Ruling.** Coordinator, 2026-11-01 20:32 CST, restored the refusal. Coordinator, 2026-11-01 21:40 CST, narrowed the refused act to the test changes the builder wrote itself: a tree rebuilt from the reflog broke wherever git combines other people's commits. Incident 95b4348b (lane page-item-checked-at-write, 2026-11-01) is pinned by the first `builder-refuse` case. Owner, 2026-11-08 12:16 CST, page item 437 a (builder-test-edit-scope): keep "builders never write test content". Measure a builder's test changes against main after the merge, not against the branch base. Main's own test changes then pass. Conflicts inside test files still go to a test-author (PR #1521). The guard meets it for a merge committed by `git commit`: that merge is judged against git's own merge of its parents (`git merge-tree`), so main's clean test changes pass. A test file that still holds conflict markers differs from that merge, so it is a builder change, refused by `builder-diff`. A merge that a strategy option commits (`git merge -X ours|theirs`, `git merge -s ours`, or a `git pull` that merges with those) writes a reflog subject the guard does not read. That gap is the open debt `builder-diff-auto-merge-reflog` (builder merge by strategy is not judged).

## What the builder wrote

`own_changes` in `hooks/guard.py` reads the HEAD reflog, and judges only what the builder made:

- **Refused.** Each commit the builder made (`commit`, `commit (amend)`, `commit (merge)`) that HEAD still holds, against its first parent. A merge commit is measured against git's own merge of its parents (`git merge-tree`), so only what the builder resolved or added counts. A test path that both sides changed and the builder resolved is refused, whichever side it kept. A write after a finished rebase is refused too, such as main's bytes written back over a test file the rebase replayed (coordinator, 2026-11-01 23:10 CST). Also the working tree and its untracked files against HEAD. While a merge is in progress, they are measured against git's own merge of HEAD and MERGE_HEAD.
- **Logged only.** A replay the builder resolved or chose: a hand-resolved cherry-pick, a revert, a rebase squash, fixup or continue. The working tree while a replay is in progress (a cherry-pick, revert, squash or rebase). A path that a rebase replayed and that holds the upstream side again, as the builder left it during the rebase (a conflict it resolved to the upstream side).
- **Not read.** A plain cherry-pick, rebase pick or `am`, a clean merge, a reset, a checkout and a pull. Each brings other people's commits.

**Known gap.** A squash merge or a `cherry-pick -n`, once committed, is a plain own commit: git removes its marker at the commit. Its test change is refused at push and stop.

**Cost.** Git reads only, plus the objects `merge-tree` writes. No timer and no long-lived process. Each commit, push and stop costs one reflog read, three rev-parse calls, one diff and one untracked list. Commits of the builder's own add one rev-list, and one parent read and one diff each. A merge commit or a merge in progress adds one `merge-tree`. Each rebase in the reflog adds one ancestry check, and two diffs while HEAD holds it. A log line is written only for an offence, a logged change or an unread state. `merge-tree --write-tree` needs git 2.38 or newer: older git reads a merge as unread.

**Measure.** `GUARD_FAMILY=builder-refuse hooks/test_guard.py`: 111 of 111 `builder-refuse` cases pass on this tip.

## Roles

The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session started with `--agent builder` (no `agent_id`) stay allowed.

- `builder`: refused at commit, push and stop when the diff holds a test path. The write tool and the shell check refuse it too. A test conflict mid-merge is refused. The route is `git merge --abort`, then report to the orchestrator.
- `test-author`: the inverse. Logged when the diff holds anything but a test path, test config, a dev dependency list or a whole workflow test step (`author-diff`). Never refused at commit, push or stop.
- `record-writer`: may change only `*.md` files: records, README, CLAUDE.md-style docs, agent files, skills and output styles. It never changes product code, tests, CI or config. The write tool refuses any other path (`record-writer-scope`). At commit, push and stop, a diff that holds one is logged only (`writer-diff`).
  - Reason: a role name is only a label on the spawn. With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and the floor means nothing (`agent-model-cap`).
- `designer`: at commit, push and stop, an offence is logged only (`designer-diff`).
- Each write refusal names no path. It says to report the needed change, and the orchestrator assigns it to another role (`git-remedy-never-names-target`).
- The orchestrator gives a test to a test-author, before or after the build. The builder reports the test change it needs and never writes it (`agents/builder.md`).
- A refusal is final: an agent never writes a refused path another way. The write tool refuses by path. At commit, push and stop, a builder's test change is judged on the builder's own change, so a test file written by shell is refused there too. Other refused paths rest on prose only (owner), in `agents/builder.md` and `agents/test-author.md`. A test-author's shell write of such a path is logged only (`author-diff`), in debt `refusal-route-around-guard` (no guard refuses a test-author that routes around a refusal).

**Test paths and test config.** The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A test-author changes them.

- A builder change to a test-runner config file that ADDS a line disabling tests counts as a test change.
- A test-author owns test config files and `requirements-dev.txt`. Two files are partly owned: `package.json` (only `devDependencies`, `jest` and the test scripts) and `pyproject.toml` (only the `[tool.pytest*]` sections).
- A builder may add a dependency or a dev dependency.
- A test-author owns a CI step that only runs a test suite. In `.github/workflows/*.yml` or `*.yaml`, it may add or remove a whole test-run step. The step holds only the keys `name`, `if`, `run`, `shell`, `working-directory` and `timeout-minutes`. Its one `run:` is a single line: an optional interpreter (`python`, `python3`, `node`, `bash`, `sh` or `pwsh`), a test path, and arguments that disable no test. No shell operators, `$(` or backtick. The write tool refuses any other workflow change by a test-author (`test-author-scope`), and commit, push and stop log it (`author-diff`). `workflow_test_steps_only` in `hooks/guard.py` judges it, reading `workflow_changed_lines`.
- A builder keeps every other workflow edit, and may add a test step or move one. Its change counts as a test change (`builder-test-edit`) when it does one of three things. It adds a test-disabling flag or name on a line that names a test runner or runs a test path. It adds `continue-on-error: true` or `if: false` under a test-run step. It drops a test path that the workflow ran before. `workflow_builder_refused` in `hooks/guard.py` judges it, through `workflow_disables_tests`, `workflow_disables_step` and `workflow_drops_tests`; the first reads `workflow_changed_lines`. The builder is not refused for the whole file, because CI work (lint and build steps) is a builder's.

**False alarms pinned** (`guard-that-cries-wolf-is-spent`). A builder may still do these:

- Rename or delete product files, and add a dependency or a script to a manifest.
- Read tests, and keep test changes that the branch inherited or that main brought in a merge. Keeping them needs no edit. A merge conflict in a test file is not the builder's to resolve: resolving it chooses what the test checks, so a test-author resolves it. The refusal names the test-author route in one sentence, and the next says a merge conflict in a test file takes the same route.
- Use a name that only looks like a test, such as `src/contest.py`.
- Write a file in no repository, such as a probe in the session scratchpad, from a call that runs in a repository. A path with no enclosing checkout is no test of the repo. A test path in any repository stays refused, also one in a different repository. A call that runs in no repository still judges the path by its shape.
- Write a document in a `spec` folder, such as `docs/spec/api.md`. `spec` is a test folder for code and fixtures only. A `.md`, `.mdx`, `.markdown`, `.txt`, `.rst` or `.adoc` file there is a document. `spec/foo_spec.rb` and `src/x.spec.ts` stay refused.

## The shell check

The shell check does not replace the act. The act stays a test path in the builder's change. The shell check flags common mistake forms first. The diff log at commit, push and stop catches every other form. Recovery stays allowed: `git checkout -- <test>` and `git restore` are not read as writes.

- Reads: a redirect, `tee`, `sed -i` or `cp` onto a test path (`_shell_write_hit` in `hooks/guard_frozen.py`, with `command_position`). It also reads a python or node heredoc body, or a `-c` or `-e` script, that opens a test path for write (`interpreter_write_hit`, same module). Both use the Edit path's predicate (`builder_test_path`, in `hooks/guard.py`).
- Basis: named incident, 2026-11-01. In lane `refusal-cite-reach`, a builder changed `lint/test_rule_audit.py` through a python heredoc. It then restored the file with `git show HEAD:... > file`.
- Landed: 2026-11-02.
- Cost: no process, no file, no timer. The scan runs inside the guard hook that already runs for a builder's shell call. `ast` is imported only when a python body is read. A refusal writes its one guard.log line, as every refusal does. A scan error in the python or node reader is no hit. Any other scan error ends the judge: the guard logs `guard-crash` and allows the call.

Kind: process
Home: hooks/guard.py
