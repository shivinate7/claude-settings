#!/usr/bin/env bash
# Runs the ruling-kind lint on the caller's checkout (the current directory) against the pull
# request base in BASE_REF. An empty BASE_REF is not a pull request: skip, by design.
# Fail closed: a base that cannot be fetched or diffed is red. CI=true makes the lint itself
# exit 1 on a git diff failure; the lint is told so here, so a local run behaves the same.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${BASE_REF:-}" ]; then
  echo "ruling-kind: no pull request base, skipped"
  exit 0
fi
root="$(git rev-parse --show-toplevel)" || { echo "ruling-kind: UNKNOWN, not a git checkout"; exit 1; }
git fetch --no-tags origin "+refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF" ||
  { echo "ruling-kind: UNKNOWN, cannot fetch base $BASE_REF"; exit 1; }
CI=true python3 "$here/../../lint/check_ruling_kind.py" --root "$root" --base "origin/$BASE_REF"
