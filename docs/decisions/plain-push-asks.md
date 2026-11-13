# A plain push asks for main or a stray branch, and is refused for an agent branch or an every-branch push that would update main or send an agent branch

## The ruling

Two kinds of push that are not forced ask. Approving a prompt lets one push through; it is not a grant. Two more are refused, with their remedy. One is a push that writes an agent-worktree branch. The other is a push of every branch that would update main or master, or would send a local agent-worktree branch. Every-branch pushes never ask. The owner's typed override lets each ask or refusal through (`owner-override`).

Sources:
- Asks: owner rulings, Cockpit, 2026-11-03 22:23 CST.
- Agent-branch refusal: see its bullet below.
- Every-branch refusal: owner ruling, page item 502, 2026-11-10 16:08 CST: "I either want it approved or declined whichever is correct. I know for a fact I dont want to be asked."
- Every-branch refusal, agent-branch part, and the source-side reading of a glob: owner answer A, 2026-11-11 09:12 CST, relayed by the coordinator at 09:14 CST. Goal: never asked, no conflicts, no lost work.

| Push | Outcome | Rule id |
|---|---|---|
| A destination named `main` or `master` (`main`, `HEAD:main`, `x:refs/heads/main`, a bare push that resolves there), on a network remote | ask | `push-main` |
| An implied destination (bare push, `HEAD`, `@`, or the current branch's own name) that differs from the branch's upstream, on the upstream's remote, and does not yet exist there | ask | `push-stray-branch` |
| A destination (implied, a colon-less refspec, or after the colon) named like an agent-worktree branch (`agent-<hex>`, `claude/agent-<hex>`, `worktree-agent-<hex>`), with or without an upstream | refuse, remedy `git push origin HEAD:<lane-branch>` | `push-agent-branch` |
| A push that names `main` and an agent-worktree branch together (`git push origin main HEAD:agent-<hex>`, `git push origin main agent-<hex>`) | refuse, remedy `git push origin HEAD:<lane-branch>` | `push-agent-branch` |
| `--all` or `--branches` from a checkout on an agent-worktree branch, to a network remote, whether or not it would update main | refuse, remedy `git push origin HEAD:<lane-branch>` | `push-agent-branch` |
| Every branch (`--all`, `--branches`, or a glob refspec such as `refs/heads/*:refs/heads/*`), to a network remote, when it would update main or master there, when a local agent-worktree branch is among the branches it sends, or when a glob or the branch list cannot be read. The agent-checkout `--all` and `--branches` row above takes precedence | refuse, remedy `git push origin HEAD:<lane-branch>` | `push-all-main` (kind `all-agent` for an agent branch sent; a failed read is kind `all`) |
| Any other plain push | allow | |

- Item 207 a, `push-main`: main moves only by pull request (`git-main-only-by-pr`). The names are
  literal, `main` and `master`. The remote's HEAD is not read. It asks only for a network remote
  (https, http, ssh, git, or `host:path`). A remote with no URL, or a local path or `file://`
  URL, is silent: git refuses the first, and the second is a test fixture, not GitHub. A remote
  the shell has not yet expanded, such as `"$REMOTE"` or `$(...)`, counts as a network remote. A double-quoted one with a space inside is blanked
  first, so it stays silent (note push-main-quoted-substitution). Source: unverified.
  A roadmap note, step `push-main-remote-check` (commit 98b97d0d98), dates the relay to 10:03 CST Nov 8,
  after a push-main ask on a fixture repo, and labels it item 410 a. Item 410 is hold-which-fixes-start
  (branch `lane-inflow-hold-carry`), a different question. The waiting page is not readable from this
  session. Checked 2026-11-12 08:53 CST.
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
  and `-u` count, and so does a bare push under `push.autoSetupRemote`. It refuses and names its
  remedy, `git push origin HEAD:<lane-branch>`. The refusal text
  goes to the session, not the owner (the principle of `guard-remedy-not-to-owner`, which records it
  for Stop refusals). Source, kind process: owner ruling, 2026-11-02, that a `worktree-agent-*`
  branch never reaches origin (32 sat on origin that day, pushed because the agent files said to
  push the worktree's own branch); the coordinator's pick (a), 2026-11-09 13:21 CST, step
  `agent-branch-push-refuses`, extends it to the `agent-<hex>` and `claude/agent-<hex>` forms (the
  2026-11-02 ruling names `worktree-agent-*` only). A test-author or builder pushing a lane-named branch
  unasked is not read here; roadmap step `push-ask-reads-brief` holds it.
- Combined push, owner ruling, chat, 2026-11-10 14:59 CST, question "Combined push", answer "Refuse it".
  A push that names `main` and an agent-worktree branch is refused as `push-agent-branch`, not asked as
  `push-main`. Controls unchanged: `main` alone asks `push-main`; `main` with a lane-named branch asks
  `push-main`; a lane branch, `HEAD:<lane-branch>`, `archive/*` and deletes are allowed.
- Every-branch push, `push-all-main`: a plain push of every branch never asks. On a network remote it is
  refused when one of the checks below holds. Otherwise it is allowed.
  - Main. It would update main or master there (owner ruling, page item 502, 2026-11-10 16:08 CST). That
    is so when local main or master exists and its remote-tracking ref
    (`refs/remotes/<remote>/<name>`) is missing or differs from it. A matching ref is trusted. The
    guard never contacts the remote. A failed ref read refuses. No local main or master allows.
  - Agent branch. A local branch named like an agent worktree (`agent-<hex>`, `claude/agent-<hex>`,
    `worktree-agent-<hex>`) is among the branches it sends (owner answer A, 2026-11-11 09:12 CST, relayed
    by the coordinator at 09:14 CST). `--all` and `--branches` send every local branch. A glob sends the
    branches its source side matches, whatever its target name: `refs/heads/*:refs/heads/lane/*` is
    refused while `worktree-agent-<hex>` exists. Worktrees of one clone share local branches, so one agent
    worktree's branch refuses from any checkout of that clone. Code: `_local_agent_branches` (the branch
    list) and `_glob_sends` (the source-side match) in `hooks/guard_push_delete.py`.
  - Unreadable. A glob that is not one `*` on each side refuses on a network remote, whether or not local
    main exists. So does a branch list that cannot be read.
  - Target decides main. A glob refspec reaches main or master only when its target names one, because
    the target is what the push writes. `refs/heads/*:refs/heads/*` does; `refs/heads/*:refs/heads/lane/*`
    does not. A glob with no colon has the same target as its source, so `refs/tags/v*` reaches no main,
    and `refs/heads/*` does.
  - The verdict is the same from a main, lane or detached checkout. From an agent checkout, `--all` and
    `--branches` are refused by `push-agent-branch`, not `push-all-main`, to a network remote, whether or
    not they would update main. The push still sends the agent branch to origin. A glob from an agent
    checkout is refused whatever its target: the checkout's own `worktree-agent-<hex>` branch is a local
    agent branch, and the glob's source matches it.
  - Silent: a dry run, a local-path remote, and a deletion. A forced form, such as `--all --force` or
    `--force origin refs/heads/*:refs/heads/*`, asks under `force-push`.
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
- A push asks only alone, or with a harmless lead or tail such as `2>&1 | tail -1`. In a longer
  chain the `ask-alone` refusal denies it: run the push on its own.
- Silent, by this lane's reading: an upstream of `main` or `master`. A branch made from
  `origin/main` tracks main (git's autoSetupMerge), so its first `git push -u origin HEAD` would
  otherwise ask on every lane.
- Silent: a bare push under `push.default=simple` with a mismatched upstream. Git refuses it
  itself.

Cost: no new long-lived process or file. The reads run per push, in the guard's own run.
- Whole-guard counts per call, all checks included. Source: `record_push_cost_case` in `tests/guard/s13406-merge.py`.
  - `--all` to a named network remote: config 2, symbolic-ref 2, for-each-ref 2, rev-parse 1. The second
    `for-each-ref` lists the local branches. It runs only when no tracking ref shows an update.
  - `--all` to a local-path remote: config 2, symbolic-ref 1, rev-parse 1.
  - A glob refspec: config 1, for-each-ref 2, rev-parse 2, symbolic-ref 1, diff 3, rev-list 1. The second
    `for-each-ref` runs under the same condition.
  - Nothing contacts the remote. No `ls-remote`, `fetch` or `push` runs.
- Added by the other pushes' reads: a literal destination of main or master reads the remote's URL with
  one `config`. A HEAD push or a bare push adds one `symbolic-ref` and one `config`. A refspec push such
  as `origin lane/foo` adds one `symbolic-ref`. One whose destination differs from its upstream adds one
  `rev-parse`, a local read of the remote-tracking ref. A remote given as a URL or path reads nothing.
- The octopus-push check (decision `octopus-push-refused`) adds one `rev-list` for each pushed ref other
  than main or master. `--all` and `--branches` name no ref.

## The mistakes

- Banchi, 2026-09-12: `git push origin HEAD` landed on a stray branch, not the upstream.
- Banchi: five plain pushes to main, outside a pull request.
- q_max lane #1102, 2026-11-08: a test-author pushed its own agent-worktree branch
  `claude/agent-a22bb0ed47825117b`, with no upstream, not the lane branch. `push-stray-branch`
  is silent with no upstream, so `push-agent-branch` refuses it. Coordinator, 01:10 CST: a fix under
  ruling 206 a. A lane branch with no upstream stays silent.
- Owner, 2026-11-09 13:14 CST: an agent-branch push prompt reached him in chat.

Risk: incident (banchi, 2026-09-12).

Kind: process
Home: hooks/guard_push_delete.py
