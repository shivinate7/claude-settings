# No guard stops an agent that routes around a refusal

**What.** A hook refuses an Edit of a path, then the same agent writes the file with Bash and Python. No hook sees a write made that way, except the builder shell early warning for test paths. Seen on 2026-10-03 in q_max: a test-author got an Edit refusal, then wrote the same file by shell. The reviewer caught it. The shell early warning for builder test writes now covers the common shell and interpreter routes, and this debt stays open for the others.

**Where.** `agents/builder.md` and `agents/test-author.md` hold the prose ("a refusal is final"). No hook backs it, except the builder shell early warning for test paths.

**Decision.** `builders-cannot-edit-tests`, builders cannot edit tests (it records the prose-only ruling).

**Retire.** Build when the owner asks for a forced guard, or a second route-around is measured. Two options:

- Fix the base defect that decision names, so the diff check refuses at stop and commit for any route. This judges the result, as that decision requires.
- Deny a shell command that names a path the same agent was refused. This judges commands, which that decision rejected.

Closed when a red case writes a refused path by shell and the guard refuses it.

## Ruling

Owner: prose only for now. One evasion is measured, and the reviewer caught it.
