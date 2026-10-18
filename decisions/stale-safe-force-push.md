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
| Any forced push whose destination is the default branch | ask |
| Any forced push whose destination cannot be resolved | ask |

The remedy reads "retry with --force-with-lease --force-if-includes". It never names the target
(`git-remedy-never-names-target`).

- A deletion at the default branch asks. A deletion elsewhere is allowed.
- `--mirror` and `--all` reach every branch, so a forced one asks.
- The default branch is the one `refs/remotes/<remote>/HEAD` names. With no such ref, it is `main` and
  `master`. With no readable repository it is unknown, and unknown is not safe, so the push asks.
- Ask, not deny, at the default branch: a rewrite of the default branch is sometimes the intent. The prompt
  is the grant, and it names no target.

Kind: process
Home: hooks/guard_push_delete.py
