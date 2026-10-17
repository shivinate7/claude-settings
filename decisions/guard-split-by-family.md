# The guard splits into one module per rule family

## The ruling

Owner, 2026-10-12 and 2026-10-13:

- Split `hooks/guard.py` first, then map changed files to test families in the CI scope job.
- Use flat files beside `guard.py`: `guard_core.py` and one `guard_<family>.py` for each family in `hooks/test_guard.py` `FAMILIES`. Why: a folder would need four installer paths changed, and the installers copy files, not folders.
- `guard.py` stays the only entry point. Every name another file imports from `guard` keeps resolving through it.
- Each split PR is proven by the full suite and the mutation harness in CI. The case list and the kill count must not drop.
- Opus builds the split, on the owner's word.
- `guard_core.py` writes the session id column in guard.log, because it holds the log code.
- The ci-hygiene skill gets a step: split the slowest suite's subject by family, and give the measured CI time before and after.

Why: the guard suite is the slowest CI job. The family filter (`GUARD_FAMILY`) cannot cut CI time while one file holds every rule.

## Holes, named

Debts: `guard-split-mutant-needs-git` (the root-scope mutant is killed only inside a git checkout), `sweep-anchor-first-match` (the sweep's apply path replaces the first anchor match only), `guard-glob-three-tools` (three tools glob the guard modules on their own), `guard-split-sibling-mutant-case` (PR2 needs a case that kills a sibling mutant).

Kind: build
Plan: decisions/guard-split-by-family.md#the-ruling (all)
Home: hooks/guard.py
