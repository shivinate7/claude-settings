# Refusal route-around stays open for roles other than builders

**What.** An agent writes a refused path by shell or interpreter. The write tool refusal does not stop it. Measured twice:

- 2026-10-03, q_max: a test-author got an Edit refusal, then wrote the same file by shell. The reviewer caught it.
- 2026-11-01, lane refusal-cite-reach: a builder changed a test file through a python heredoc before its Edit call was refused. It disclosed and restored the file.

**Where.** `agents/builder.md` and `agents/test-author.md` hold the prose ("a refusal is final").

**Closed for builders.** Guard rule `builder-test-edit` denies a builder's shell write to a test path, as an early warning. The diff stays the result (`builders-cannot-edit-tests`).

**Open.** A route-around by test-author, record-writer or designer. A program's own code that writes a refused path (`python3 script.py`) is not read.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests. It holds the ruling for each role.

**Retire.** The retire condition, a second route-around measured, was met on 2026-11-01. Its builder case is built. For the open part, two options:

- Fix the base defect that decision names, so the diff check refuses at stop and commit for any route. This judges the result, as that decision requires.
- Deny a shell command that names a path the same agent was refused. This judges commands, which that decision rejected. Built for a builder's test paths only (`builder-test-edit`).

Closed for each open role when a red case writes a refused path by shell and the guard refuses it.

## Ruling

Owner: prose only for now. Measured route-arounds: 2026-10-03 (q_max, test-author, reviewer caught it) and 2026-11-01 (lane refusal-cite-reach, builder, disclosed and restored the file).
