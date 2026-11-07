# No guard refuses a test-author that routes around a refusal

**What.** A test-author gets a refusal on an Edit of a path, then writes the same file with Bash and Python. Commit, push and stop log that act only, as `author-diff`, and never refuse it. Seen on 2026-10-03 in q_max: a test-author got an Edit refusal, then wrote the same file by shell. The reviewer caught it. A builder's shell write to a test path is refused early (`builders-cannot-edit-tests` (builders cannot edit tests)), for the common shell and interpreter routes. This debt stays open for the test-author's routes.

**Where.** `hooks/guard.py`: `diff_refusal` logs a test-author's own change as `author-diff` and never refuses it (`diff_rule`). The write tool refuses a test-author's Edit of a non-test path (`AUTHOR_SCOPE_REASON`, rule `test-author-scope`). The prose ("a refusal is final") is in `agents/builder.md` and `agents/test-author.md`. No hook refuses a test-author's shell write of a refused path.

- **Decision.** `builders-cannot-edit-tests` (builders cannot edit tests). It records the prose-only ruling for other refused paths, and points here.

**Retire.** Build when the owner asks for a forced guard, or a second route-around is measured. Two options:

- Refuse the test-author's own change at commit, push and stop, for any route, as `builder-diff` does for a builder. This judges the result, as that decision requires.
- Deny a shell command that names a path the same agent was refused. This judges commands, which that decision rejected.

Closed when a red case writes a refused path by shell and the guard refuses it.

## Ruling

Owner: prose only for now. One evasion is measured, and the reviewer caught it.
