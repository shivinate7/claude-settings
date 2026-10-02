# Builders cannot edit tests

## Outcome protected

A builder that cannot pass a test must not delete it, skip it, or rewrite it to pass. A green
run must mean the code is right. ImpossibleBench (arXiv 2510.20270) measured it: read-only
tests block direct test edits with little loss of real performance.

## The rule

`hooks/guard.py`, rule name `builder-test-edit`, denies a call when ALL of these hold:

- The payload carries an `agent_id` and an `agent_type` of `builder`. The main session,
  reviewers, and other agent types stay allowed. A session started with `--agent builder`
  has no `agent_id`, so it stays allowed.
- A write tool (Edit, Write, MultiEdit, NotebookEdit) targets a test path. Or a Bash or
  PowerShell segment deletes, moves, rewrites, or redirects onto one. The shell writers are
  `rm`, `mv`, `tee`, `truncate`, `sed -i`, `perl -i`, a redirect, the PowerShell writers,
  `git rm`, and `git mv`. A `cp` or `install` counts when its LAST argument is a test path.
- Or an edit adds a skip marker to `conftest.py`.

The reason says: report the needed test change; the orchestrator assigns it to a non-builder.
It names no path (rule git-remedy-never-names-target).

## Test path

The guard reads the path's own parts, never a substring (decisions/predicate-is-the-act.md).
A basename is `test_*.py`, `*_test.py`, `*_test.go`, `*.test.{ts,js,tsx,jsx}`, or `*.spec.*`.
A directory part is `tests`, `test`, `__tests__`, or `spec`. Parts count from the nearest
parent that holds `.git`. So a clone under a folder named `tests` is not all test files.

## False alarms pinned (decisions/guard-that-cries-wolf-is-spent.md)

These stay allowed: `cat tests/x.py`, `cp tests/a.py /tmp`, `sed -n ... tests/x.py`,
`rm contest.py`, an edit of `latest_results.md`, `attest.md`, or `testing.py`, and a Read of
a test.

## Known ceilings (bandaids, named)

- A rewrite through an interpreter (`python -c`) is not read. A `>` quoted inside an `echo`
  is not read either. The editor tools and common shell writers are the judged routes.
- Skip markers are read only in `conftest.py`. Anywhere else a marker needs a test path, which
  is already refused. A scan of every file would flag prose and this guard's own source.
- `spec` as a directory also covers design-spec folders. The brief chose this.
- The guard's own suites (`hooks/test_guard.py`, `lint/test_*.py`) are test paths. A builder
  briefed to change them is refused. The orchestrator assigns that edit to a non-builder.

## Test author

The orchestrator's chosen test author writes a new test, before or after the build. The
builder never writes it (`agents/builder.md`).
