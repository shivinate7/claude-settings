# A plain push asks when it writes main or a stray branch

## The ruling

Two pushes that are not forced ask. Approving the prompt lets one push through; it is not a grant.
The owner's typed override lets each through (`owner-override`). Owner rulings, Cockpit, 2026-11-03 22:23 CST.

| Push | Outcome | Rule id |
|---|---|---|
| A destination named `main` or `master` (`main`, `HEAD:main`, `x:refs/heads/main`, a bare push that resolves there, `--all`, `--branches`) | ask | `push-main` |
| An implied destination (bare push, `HEAD`, `@`, or the current branch's own name) that differs from the branch's upstream, on the upstream's remote | ask | `push-stray-branch` |
| Any other plain push | allow | |

- Item 207 a, `push-main`: main moves only by pull request (`git-main-only-by-pr`). The names are
  literal, `main` and `master`. The remote's HEAD is not read.
- Item 206 a, `push-stray-branch`: `git push origin HEAD` writes the local branch's name, not its
  upstream. Measured 2026-11-03: local `mylocal` tracking `origin/lane/x` made a new remote branch
  `mylocal`.
- Silent:
  - a push to the branch's own upstream;
  - a first push with no upstream;
  - a `-u` push whose destination is the local branch's own name, even when the branch tracks
    another lane. It sets the new upstream on purpose. Source: coordinator brief, 2026-11-03
    22:23 CST, as clarified 2026-11-04 01:49 CST;
  - an explicit `HEAD:<branch>` (agents push this way);
  - `archive/*`, and `--tags` (for these two rules; an archive push of a branch with an unarchived remote
    tip is refused by `archive-remote-tip`, decision `archive-remote-tip`);
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
destination reads nothing new. A refspec push such as `origin lane/foo` adds one `symbolic-ref`.
A `HEAD` push or a bare push adds one `symbolic-ref` and one `config`. `record_push_cost_case` in
`hooks/test_guard.py` proves the counts.

## The mistakes

- Banchi, 2026-09-12: `git push origin HEAD` landed on a stray branch, not the upstream.
- Banchi: five plain pushes to main, outside a pull request.

Risk: incident (banchi, 2026-09-12).

Kind: process
Home: hooks/guard_push_delete.py
