# A forced push is safe when it cannot overwrite newer work

CLAUDE.md says: "Judge every rule, check, and design by the outcome for the person the
software serves." The outcome here: the owner gets no prompt for a safe push, and no push
overwrites newer remote work with a stale copy. This entry replaces the old rule, which
asked on every forced push. That prompt protected nothing the lease does not protect, and
it fired on every safe rebase. A guard that fires when nothing is wrong is spent. See
decisions/guard-that-cries-wolf-is-spent.md.

## The outcomes

The guard resolves the act, not substrings. See decisions/predicate-is-the-act.md. It reads
the flags and the refspecs of each `git push` call. Quoted text, heredocs, and
`git log --grep=--force` are not a push.

| Push | Outcome |
|---|---|
| Not forced | allow |
| `--force-with-lease` (bare, `=<ref>`) with `--force-if-includes`, off the default branch | allow |
| `--force-with-lease=<ref>:<sha>`, off the default branch | allow, alone |
| `--force`, `-f`, a `--fo` prefix, `+refspec` | deny, with a remedy |
| A lease without `--force-if-includes` and without a sha | deny, with a remedy |
| Any forced push whose destination is the default branch | ask |
| Any forced push whose destination cannot be resolved | ask |

The remedy reads "retry with --force-with-lease --force-if-includes". It never names the
target (CLAUDE.md, git-remedy-never-names-target).

## How the destination is resolved

- A refspec `src:dst` goes to `dst`. A bare `src` goes to `src`. A leading `+` and a
  `refs/heads/` prefix drop off. A quoted single-word refspec or remote is unquoted first.
- `HEAD` resolves to the current branch. A detached HEAD has none, so the push asks.
- No refspec: read `push.default` with `git config`. `simple`, `current`, or unset: the
  current branch. `upstream`: the branch's `branch.<name>.merge`. Anything else (`matching`,
  `nothing`, no upstream, an unreadable config) asks.
- `--repo=<remote>` or `--repo <remote>` names the remote. Every plain word is then a refspec.
- A deletion (`--delete`, `-d`, `:dst`) at the default branch asks. A deletion elsewhere
  is allowed.
- `--no-force-if-includes` and `--no-force-with-lease` cancel the flag before them.
  `-ofoo` and `-o foo` are push options, never `-f`.
- `--mirror` and `--all` reach every branch, so a forced one asks. `--mirror` forces by
  itself.
- A glob destination asks.

## How the default branch is resolved

1. `refs/remotes/<remote>/HEAD`, with the remote named in the push (`origin` when none).
2. No such ref in a readable repository: `main` and `master`.
3. No readable repository: unknown. Unknown is not safe, so the push asks.

## Why ask, not deny, at the default branch

The owner changed the first design, which denied. A rewrite of the default branch is
sometimes the intent. The prompt is the grant. The prompt names no target.

## What would date this entry

- Git older than 2.30 lacks `--force-if-includes`. On such a git the remedy fails. Measured
  on git 2.54.0 only, never on an older one: unmeasured.
- A lease with a sha guards the one ref it names. A push of another ref beside it is not
  guarded. This design accepts that for the sha form, as briefed.
- Known gaps. A push through a shell alias, a git alias, or `sh -c "..."` is not read.
  Quoted multi-word text is blanked, so a push inside it is not read either. Shell
  variables and command substitution in a refspec are not expanded.
- The target is the push's own `git -C <dir>`, else the command's last `cd`, else the session's
  cwd. A `-c key=value` on the call overrides config. A directory that is not there asks.
  Several `-C` on one call and a `cd` inside a subshell are not followed.
- Gap: a refspec `src:heads/main` (short form of the full ref) is not matched as the default
  branch.
- Gap: `remote.<name>.push` config (for example `HEAD:main`) sets the refspec of a bare push
  and is not read.
- Both gaps are exotic. Git's own lease plus `--force-if-includes` still protects the remote.

## Checks

`hooks/test_guard.py` holds a case for each row above, and the false alarms. The mutants in
`hooks/mutate_guard.py` named `force-push:` kill each branch of `push_verdict`.
