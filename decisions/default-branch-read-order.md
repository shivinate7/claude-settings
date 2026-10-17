# Default branch read order

Kind: process
Home: hooks/guard_core.py

## The question

Which ref is the repository's default branch, for the branch-delete rule, the janitor sweep and
the push guard?

## The ruling

Owner, 2026-10-16: read in this order. The first ref that resolves wins.

1. `<remote>/HEAD`, when it resolves.
2. `<remote>/main`.
3. `<remote>/master`.
4. Local `main`.
5. Local `master`.

- `<remote>` is `origin` for the branch-delete rule and the sweep. The push guard reads the
  PUSHED remote: the named remote, else the branch's configured remote, else `origin`.
- A dangling `<remote>/HEAD` falls through to step 2. It never makes a base unreadable.
- A verify that git could not run is unreadable (None), never "does not exist".
- One home: `resolve_default_base`, over `read_default_base`. The push guard calls
  `read_default_base`. Only a resolved `<remote>/HEAD` names one branch for it. Any other
  answer, or none (HEAD unset or dangling, an unreadable read), protects both `main` and
  `master`, and the name HEAD holds when it holds one.

## Why

A dangling `origin/HEAD` hid the default branch. A push to `main` read as allowed, and a
squash-merged lane was never freed. A repository that has `origin/main` may still hold
`master`, so a missing HEAD protects both names.

## Holes, named

1. A verify that cannot run after an earlier step answered "no" has no test. The code returns unknown, so the sweep refuses the repo and the push guard protects main, master and the HEAD name. It fails safe. Debt: `base-read-midway-untested`, the midway unreadable path has no test.
2. The push guard reads the current branch with `symbolic-ref --short HEAD`. A tag named like that branch makes git print `heads/<name>`, and a lease push of `HEAD` then allows. Main has the same gap. Claude would need a tag named exactly like the default branch. Debt: `push-head-tag-misread`, a same-name tag misreads HEAD.
