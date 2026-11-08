# A push that creates a new branch at another branch's tip is refused

## The ruling

Rule `push-new-branch` denies a push whose refspec creates a branch name the remote does not hold, at the commit that a branch the remote holds already points to. Source: lane `nfp-push-chain-guards`; coordinator rulings, 2026-11-08 09:20, 13:35 and 14:45 CST, as narrowed by the lane's pick at 14:57 CST.

The mistake: a pull request head's sha pushed to a new branch name instead of to the PR's own branch. Example: `skc-ste` created at `02c93f63d`. A cloud session cannot delete a remote branch, so the stray stays until a session on Shivam's computer removes it.

| Refspec | Outcome |
|---|---|
| A new destination, source a sha, a remote-tracking ref (`origin/x`, `refs/remotes/...`) or a revision expression (`HEAD~1`, `<sha>^`, `HEAD@{1}`), at another branch's tip. A `+` form is judged too. | deny |
| Anything else | main's verdict (`plain-push-asks`) |

Judged only when the source is a sha, a remote-tracking ref or a revision expression. `HEAD`, `@` and a plain local-branch name are left as main treats them: an explicit `HEAD:<branch>` is silent (decision `plain-push-asks`).

Exempt, each held by its own case in `hooks/test_guard.py`:

- a destination named `archive/*`, the remedy the reason names;
- a destination that already exists on the remote, which includes a source pushed to its own name;
- a local branch pushed to its own name (not a judged source);
- a destination `main` or `master`, which `push-main` asks about;
- a source at the tip of `main` or `master`, or of the branch `origin/HEAD` names. That tip holds no work. The batch runner's first push of an integration branch is this push;
- a tag or any non-branch destination, a deletion, a glob, a colon-less push, `--all`, a mirror, a remote named by URL, and any read that fails;
- `--force` and a lease, which the force rule judges.

Stated limit: `HEAD:<new>` at another branch's tip stays as main allows it (coordinator, 14:45 CST; `plain-push-asks`). A session that pushes `HEAD` to a new name on a PR's head commit is not caught. This rule judges only what it can name by sha or remote ref. It also removes the false alarm on a chain that switches to a new branch, commits, then pushes `HEAD:new`.

Stated limit: a short `<other>/x` source from a remote other than the pushed one is not judged. Its full `refs/remotes/<other>/x` form is judged, against the pushed remote's tips.

Stated limit: a stale `refs/remotes/<remote>/*` ref (branch deleted on the remote, not pruned) still counts as a tip. A push of that sha to a new name is refused. The owner's typed `override` lifts it.

Stated limit: with origin/HEAD unset and a trunk named neither main nor master, the trunk's tip is not exempt. The `HEAD:<new>` form is unaffected: it is never judged.

Cost: no long-lived process, no file written. A judged refspec runs one `rev-parse` only when its destination is a new branch name. A tag or other non-branch ref, `main`, `master`, a branch the remote already holds, and an `archive/` name return before it. The remote's tips come from the ref files, with `for-each-ref` only for a layout the file read does not know (reftable). The default-branch read (`rev-parse --git-dir`, `symbolic-ref`, then `rev-parse` per candidate) runs once per push, and only when a judged sha sits at a remote tip. It reads local refs only and never the network.

## The mistakes

- Banchi: a stray branch `skc-ste` made at another branch's tip, 02c93f63d. The cloud cannot delete it.

Risk: incident (stray branch skc-ste, 02c93f63d).

Kind: process
Home: hooks/guard_push_delete.py
