# A plain push asks when it writes main or a stray branch

## The ruling

Three kinds of push that are not forced ask. Approving the prompt lets one push through; it is not a grant.
The owner's typed override lets each through (`owner-override`). Owner rulings, Cockpit, 2026-11-03 22:23 CST, for the first two; the third has its source below.

| Push | Outcome | Rule id |
|---|---|---|
| A destination named `main` or `master` (`main`, `HEAD:main`, `x:refs/heads/main`, a bare push that resolves there, `--all`, `--branches`) | ask | `push-main` |
| An implied destination (bare push, `HEAD`, `@`, or the current branch's own name) that differs from the branch's upstream, on the upstream's remote, and does not yet exist there | ask | `push-stray-branch` |
| A destination (implied, a colon-less refspec, or after the colon) named like an agent-worktree branch (`agent-<hex>`, `claude/agent-<hex>`, `worktree-agent-<hex>`), with or without an upstream | ask | `push-agent-branch` |
| Any other plain push | allow | |

- Item 207 a, `push-main`: main moves only by pull request (`git-main-only-by-pr`). The names are
  literal, `main` and `master`. The remote's HEAD is not read. It asks only for a network remote
  (https, http, ssh, git, or `host:path`). A remote with no URL, or a local path or `file://`
  URL, is silent: git refuses the first, and the second is a test fixture, not GitHub. Source:
  coordinator, 2026-11-08 10:03 CST, item 410 a, after a push-main ask on a fixture repo.
- Item 206 a, `push-stray-branch`: `git push origin HEAD` writes the local branch's name, not its
  upstream. Measured 2026-11-03: local `mylocal` tracking `origin/lane/x` made a new remote branch
  `mylocal`.
- Item 432 a, `push-stray-branch` narrowed: owner, 2026-11-08 11:49 CST, pick a, "skip existing
  branches". A destination that already exists on the pushed remote (read from the local
  `refs/remotes/<remote>/<name>`) is silent: that push lands on a branch that is already there,
  such as the lane's own PR branch, and makes no stray one. A failed read keeps the ask. The
  owner's note, "shouldn't it stay quiet regardless?", is not this ruling: quiet regardless would
  drop the ask for a push that makes a new branch. The ask's remedy names `HEAD:<branch>`.
- `push-agent-branch`: a push that writes an agent-worktree name puts a stray branch on the remote. Bare
  and `-u` count, and so does a bare push under `push.autoSetupRemote`. Source: coordinator, 2026-11-08
  01:10 CST, under item 206 a. A test-author or builder pushing a lane-named branch unasked is
  not read here; roadmap step `push-ask-reads-brief` holds it.
- Silent:
  - a push to the branch's own upstream, unless that name is an agent-worktree name;
  - a first push with no upstream, unless its destination is an agent-worktree name;
  - a `-u` push whose destination is the local branch's own name, not an agent-worktree name, even when the branch tracks
    another lane. It sets the new upstream on purpose. Source: coordinator brief, 2026-11-03
    22:23 CST, as clarified 2026-11-04 01:49 CST;
  - an explicit `HEAD:<branch>` to a lane branch (agents push this way);
  - `archive/*`, and `--tags`;
  - a push to another remote than the upstream's;
  - `--dry-run`, which writes nothing;
  - `push.default=matching`, whose destination is not read;
  - a plain push whose destination cannot be resolved.
- A glob refspec such as `refs/heads/*:refs/heads/*` is not read either. Claude does not write it
  in normal work.
- A push asks only alone, or with a harmless lead or tail such as `2>&1 | tail -1`. In a longer
  chain the `ask-alone` refusal denies it: run the push on its own.
- Silent, by this lane's reading: an upstream of `main` or `master`. A branch made from
  `origin/main` tracks main (git's autoSetupMerge), so its first `git push -u origin HEAD` would
  otherwise ask on every lane.
- Silent: a bare push under `push.default=simple` with a mismatched upstream. Git refuses it
  itself.

Cost: no new process or file. The reads run per push, in the guard's own run. A literal
destination reads nothing new, except a push to main or master, which reads the remote's URL
with one `config`. A remote given as a URL or path reads nothing. A refspec push such as `origin lane/foo` adds one `symbolic-ref`.
A `HEAD` push or a bare push adds one `symbolic-ref` and one `config`. One whose destination
differs from its upstream adds one `rev-parse`, a local read of the remote-tracking ref. `record_push_cost_case` in
`hooks/test_guard.py` proves the counts.

## The mistakes

- Banchi, 2026-09-12: `git push origin HEAD` landed on a stray branch, not the upstream.
- Banchi: five plain pushes to main, outside a pull request.
- q_max lane #1102, 2026-11-08: a test-author pushed its own agent-worktree branch
  `claude/agent-a22bb0ed47825117b`, with no upstream, not the lane branch. `push-stray-branch`
  is silent with no upstream, so `push-agent-branch` asks. Coordinator, 01:10 CST: a fix under
  ruling 206 a. A lane branch with no upstream stays silent.

Risk: incident (banchi, 2026-09-12).

Kind: process
Home: hooks/guard_push_delete.py
