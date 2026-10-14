# The guard splits into one module per rule family

## The question

How does CI run only the guard tests that a change touches?

## The ruling

Owner, 2026-10-12 and 2026-10-13:

- Split `hooks/guard.py` first, then map changed files to test families in the CI scope job.
  A family map on the old layout saves time only on test-only PRs, because every rule lives
  in one file.
- Use flat files beside `guard.py`: `guard_core.py` and one `guard_<family>.py` for each
  family in `hooks/test_guard.py` `FAMILIES`. A folder would need four installer paths
  changed, and the installers copy files, not folders.
- `guard.py` stays the only entry point. Every name another file imports from `guard` keeps
  resolving through it.
- Do it in small PRs. Each one is proven by the full suite and the mutation harness in CI.
  The case list and the kill count must not drop.
- Opus builds the split, on the owner's word.
- The session id column in guard.log is written by `guard_core.py`, which holds the log code.
- When the split lands, the ci-hygiene skill gets a new step. It says to split the slowest
  suite's subject by family, and gives the measured CI time before and after.

## Steps

The plan lives in the owner's plan file `guard-split-plan.md`. PR0 is the prep. The mutation
tools and the lints read every `hooks/guard*.py`. Each mutant's anchor must match exactly
once across them. PR1 maps `hooks/guard_*.py` in the scope job. PR2 extracts the
core. PR3 to PR5 move the families. PR6 and PR7 map each module to its family.

## Why

The guard suite is the slowest CI job. The family filter (`GUARD_FAMILY`) can already run
one family, but CI cannot use it while one file holds every rule. Measured on 2026-10-12:
the full suite took 929 s on the branch and 1123 s on main, on this box.

## Holes, named

Debts: `guard-split-mutant-needs-git` (the root-scope mutant is killed only inside a git checkout), `sweep-anchor-first-match` (the sweep's apply path replaces the first anchor match only), `guard-glob-three-tools` (three tools glob the guard modules on their own), `guard-split-sibling-mutant-case` (PR2 needs a case that kills a sibling mutant).

Kind: process
Home: hooks/guard.py
