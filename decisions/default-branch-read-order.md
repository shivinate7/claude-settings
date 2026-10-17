# Default branch read order

## The ruling

Owner, 2026-10-16: the branch-delete rule, the janitor sweep and the push guard read the default branch in this order. The first ref that resolves wins.

1. `<remote>/HEAD`, when it resolves.
2. `<remote>/main`.
3. `<remote>/master`.
4. Local `main`.
5. Local `master`.

- `<remote>` is `origin` for the branch-delete rule and the sweep. The push guard reads the PUSHED remote: the named remote, else the branch's configured remote, else `origin`.
- A dangling `<remote>/HEAD` falls through to step 2. It never makes a base unreadable.
- A verify that git could not run is unreadable (None), never "does not exist".
- One home: `resolve_default_base`, over `read_default_base`. The push guard calls `read_default_base`. Only a resolved `<remote>/HEAD` names one branch for it. Any other answer, or none, protects both `main` and `master`, and the name HEAD holds when it holds one.

Why: a dangling `origin/HEAD` hid the default branch, and a repository with `origin/main` may still hold `master`.

Kind: process
Home: hooks/guard_core.py
