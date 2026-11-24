# A forced push is safe when it cannot overwrite newer work

## The ruling

The owner gets no prompt for a safe push, and no push overwrites newer remote work with a stale copy.
Reason: the lease already protects newer work, so a prompt on every forced push protected nothing more
and fired on every safe rebase (guard-that-cries-wolf-is-spent).

The guard resolves the act, not substrings (predicate-is-the-act). It reads the flags and the refspecs of
each `git push` call. Quoted text, heredocs and `git log --grep=--force` are not a push.

| Push | Outcome |
|---|---|
| Not forced | allow |
| `--force-with-lease` (bare, `=<ref>`) with `--force-if-includes`, off the default branch | allow |
| `--force-with-lease=<ref>:<sha>`, off the default branch | allow, alone |
| `--force`, `-f`, a `--fo` prefix, `+refspec` | deny, with a remedy |
| A lease without `--force-if-includes` and without a sha | deny, with a remedy |
| Any forced push whose destination is the default branch | deny, with a remedy |
| Any forced push whose destination cannot be resolved | deny, with a remedy |

The remedy reads "retry with --force-with-lease --force-if-includes". It never names the target
(`git-remedy-never-names-target`).

- A deletion at the default branch is denied under `force-push`, and its reason names a forced push (note `push-delete-main-wrong-reason`). A deletion elsewhere is allowed.
- `--mirror` and `--all` reach every branch, so a forced one is denied.
- The default branch is the one `refs/remotes/<remote>/HEAD` names. With no such ref, it is `main` and
  `master`. With no readable repository it is unknown, and unknown is not safe, so the push is denied.
- Deny, not ask, at the default branch (owner, 2026-11-23 11:07 CST): no prompt grants a forced push to it. The refusal
  names the lane's own branch as the remedy, never the target.

Kind: process
Home: hooks/guard_push_delete.py
