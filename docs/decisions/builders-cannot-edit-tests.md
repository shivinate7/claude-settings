# Builders cannot edit tests

## The ruling

A builder that cannot pass a test must not delete, skip or rewrite it. A green run must mean the code is right. The guard stops ACCIDENTAL test edits (`guard-guards-mistakes-only`: every guard stops mistakes, not attacker-crafted forms). The reviewer reads every diff.

Judge the result, not the commands. The act is a test path in the diff (`predicate-is-the-act`: the predicate is the act, not the shape of the command). The shell early warning below covers the listed forms only. The diff check still judges every other form.

`hooks/guard.py` judges a builder's writes at two early warnings, before a write. It reads the diff at two points, after a write.

Early warnings:

- A write tool call (Edit, Write, MultiEdit, NotebookEdit). It DENIES, by path. Every path field the call carries is judged. Every refusal runs on all fields before any ask, so a decoy field cannot hide a refused path.
- A builder's shell call (Bash, PowerShell) that writes, removes or moves a test path. It DENIES. See the shell early warning.

Diff points:

- A builder's `git commit` and `git push` (PreToolUse, Bash and PowerShell). It LOGS.
- A builder's SubagentStop. It LOGS.

Owner, 2026-10-02: at commit, push and stop, an offence writes one `noted` log line, tagged `builder-diff` or `author-diff`, with the path. The guard allows the act. An unreadable diff logs a `role-diff-unread` line. The reviewer reads the log and the diff. Reason: the base can be wrong, and a refusal on a wrong base is a false alarm (`verification-cry-wolf-guard-is-spent`: a guard that fires when nothing is wrong is spent). Restore the refusal when the base defect is fixed, with the undo route and the once-only stop.

**Shell early warning.** For a builder, a Bash or PowerShell call is DENIED when it writes, removes or moves a test path. The code and reason match the write tool.

- It judges these forms:
  - A redirect (`>`, `>>`) to a test path.
  - `tee` to a test path.
  - `sed -i` or `sed --in-place` on a test path.
  - `perl -pi` on a test path.
  - `rm` and `mv` of a test path.
  - A heredoc header that redirects to a test path.
  - A heredoc run by a shell (`bash <<EOF`) that writes a test path.
  - An interpreter (python, node) that opens a test path for writing. The code is a heredoc body, or follows `-c` or `-e`.
  - A literal join that builds a test path: `os.path.join`, `+`, or an f-string with no fields.
  - A write target that is a glob. The glob expands in the repo.
- The path test is `is_test_rel`, the same test the write tool uses.
- Python code is read with Python's own parser. A body that does not parse is allowed. Guards stop mistakes, not attackers.
- A path outside the repo is not judged.
- A mutating word that is only an argument is not a write. `grep copy x` passes.
- Reads, prints, and writes to non-test files pass.
- Test config is not judged here. The check reads no config content. The diff at commit, push and stop still logs it.

**Residual gaps.** The guard allows these forms. The diff at commit, push and stop still logs each:

- A body piped in, such as `cat <<EOF | python3 -`.
- A subshell, `( … )`.
- `>|`.
- Async `fs.writeFile`, `fs.copyFileSync`, and `os.open`.
- A loop variable, or any other path computed at run time.
- `xargs`, and `find -exec`.
- A script written, then run.

**Roles.** The payload must carry an `agent_id`. The main session, reviewers, Explore, and a session started with `--agent builder` (no `agent_id`) stay allowed.

- `builder`: logged when the diff holds a test path. The write tool and the shell early warning refuse the write itself.
- `test-author`: the inverse. Logged when the diff holds anything but a test path, test config or a dev dependency list.
- `record-writer`: may change only `*.md` files: records, README, CLAUDE.md-style docs, agent files, skills and output styles. It never changes product code, tests, CI or config. The write tool refuses any other path (`record-writer-scope`: the record-writer's file scope). A diff that holds one is logged as `writer-diff` at commit, push or stop.
  - Reason: a role name is only a label on the spawn. With no path limit, a Haiku `record-writer` is a Haiku builder under a new name, and the floor means nothing (`agent-model-cap`: the model cap per role).
- Each refusal, write tool or shell, names no path. It says to report the needed change, and the orchestrator assigns it to another role (`git-remedy-never-names-target`: a remedy never names the forbidden target).
- The orchestrator gives a test to a test-author, before or after the build. The builder reports the test change it needs and never writes it (`agents/builder.md`).
- A refusal is final: an agent never writes a refused path another way. The guard denies the shell forms that the shell early warning judges. Every other route is prose only (owner), in `agents/builder.md` and `agents/test-author.md`. Debt `refusal-route-around-guard` (an agent redoes a refused edit with Bash and Python) holds the forced-guard option.

**Test paths and test config.** `is_test_rel` in `hooks/guard.py` decides a test path. The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A test-author changes them.

- A builder change to a test-runner config file that ADDS a line disabling tests counts as a test change.
- A test-author owns test config files and `requirements-dev.txt`. Two files are partly owned: `package.json` (only `devDependencies`, `jest` and the test scripts) and `pyproject.toml` (only the `[tool.pytest*]` sections).
- A builder may add a dependency or a dev dependency.

**False alarms pinned** (decision `guard-that-cries-wolf-is-spent`: a guard that fires when nothing is wrong is spent). A builder may still do these:

- Rename or delete product files, and add a dependency or a script to a manifest.
- Read tests, and keep test changes that the branch inherited or that main brought in a merge. Keeping them needs no edit. A merge conflict in a test file is not the builder's: resolving it chooses what the test checks, so a test-author resolves it. The refusal says so.
- Use a name that only looks like a test, such as `src/contest.py`.

Basis: incident, 2026-11-01. Lane `refusal-cite-reach`: a builder changed `lint/test_rule_audit.py` through a Python heredoc, before the Edit refusal. Landed 2026-11-02.

Kind: process
Home: hooks/guard.py
