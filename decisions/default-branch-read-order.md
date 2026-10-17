# Default branch read order

Kind: process
Home: hooks/guard_core.py

## The question

Which ref is the repository's default branch, for the branch-delete rule, the janitor sweep and
the push guard?

## The ruling

Owner, 2026-10-16: read in this order. The first ref that resolves wins.

1. `origin/HEAD`, when it resolves.
2. `origin/main`.
3. `origin/master`.
4. Local `main`.
5. Local `master`.

- A dangling `origin/HEAD` falls through to step 2. It never makes a base unreadable.
- A verify that git could not run is unreadable (None), never "does not exist".
- One home: `resolve_default_base`. The push guard calls it. It names a branch from a remote
  ref, and falls back to `main` and `master` for a local ref or no answer.

## Why

A dangling `origin/HEAD` hid the default branch. A push to `main` read as allowed, and a
squash-merged lane was never freed.

## Limits

The home reads `origin` only. A push to another remote reads the default branch of `origin`.
