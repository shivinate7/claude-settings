#!/usr/bin/env bash
# The stable mover's one step. Run in a checkout whose origin is the repo. HEAD_SHA is the commit of a
# finished main run and RUN_CONCLUSION is that run's conclusion. It moves origin's stable branch to
# HEAD_SHA only when the run succeeded, HEAD_SHA is on origin's main, and HEAD_SHA descends from stable (a
# fast-forward). GH_TOKEN, when set, authenticates the push; a local origin needs none.
set -u
head="${HEAD_SHA:-}"
conclusion="${RUN_CONCLUSION:-}"

[ -n "$head" ] || { echo "stable-mover: HEAD_SHA is not set" >&2; exit 2; }
if [ "$conclusion" != "success" ]; then
  echo "stable-mover: refused: the run concluded '${conclusion:-unknown}', not 'success'; stable stays where it is" >&2
  exit 1
fi
git cat-file -e "$head^{commit}" 2>/dev/null || { echo "stable-mover: refused: $head is not a commit in this checkout" >&2; exit 1; }

# A read that fails is UNKNOWN, never "stable is absent": only a clean read of a missing ref lets stable be created.
remote_stable=$(git ls-remote --heads origin refs/heads/stable) || { echo "stable-mover: UNKNOWN: cannot read origin's stable" >&2; exit 2; }
if [ -n "$remote_stable" ]; then
  git fetch origin "+refs/heads/stable:refs/remotes/origin/stable" || { echo "stable-mover: UNKNOWN: fetch of stable failed" >&2; exit 2; }
  stable=$(git rev-parse "refs/remotes/origin/stable")
  if git merge-base --is-ancestor "$head" "$stable"; then
    echo "stable-mover: stable is already at or past $head; nothing to move"
    exit 0
  fi
  if ! git merge-base --is-ancestor "$stable" "$head"; then
    echo "stable-mover: refused: $head does not descend from stable ($stable); stable stays where it is" >&2
    exit 1
  fi
fi

# Only a commit that origin's main holds may become stable. An unreadable main is UNKNOWN, never a pass.
git fetch origin "+refs/heads/main:refs/remotes/origin/main" || { echo "stable-mover: UNKNOWN: fetch of main failed" >&2; exit 2; }
if ! git merge-base --is-ancestor "$head" "refs/remotes/origin/main"; then
  echo "stable-mover: refused: $head is not on origin's main; stable stays where it is" >&2
  exit 1
fi

# No --force: git refuses a non-fast-forward even if the check above raced another move.
push=(git)
if [ -n "${GH_TOKEN:-}" ]; then
  auth=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
  push+=(-c "http.extraheader=AUTHORIZATION: basic $auth")
fi
"${push[@]}" push origin "$head:refs/heads/stable" || { echo "stable-mover: the push to stable failed" >&2; exit 1; }
echo "stable-mover: stable is now $head"
