#!/usr/bin/env bash
# Runs the silent-undo lint on the caller's checkout (the current directory) for the pull request
# in BASE_REF and HEAD_SHA. An empty BASE_REF is not a pull request: skip, by design.
# HEAD_SHA is the pull request head. On a pull_request run the checkout is a merge commit, so the
# lint reads the head the caller names, not HEAD. PR_BODY (the pull request body) and GH_TOKEN reach the lint
# through the environment, never a command line. --strict makes an unreadable history red:
# a check that cannot run must never pass.
# The base is the local origin/$BASE_REF when it exists. Fetch only when it is missing: a caller
# checkout with persist-credentials: false has no credentials, so a fetch of it would fail.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
if [ -z "${BASE_REF:-}" ]; then
  echo "silent-undo: no pull request base, skipped"
  exit 0
fi
root="$(git rev-parse --show-toplevel)" || { echo "silent-undo: UNKNOWN, not a git checkout"; exit 1; }
if ! git rev-parse --verify -q "refs/remotes/origin/$BASE_REF" > /dev/null; then
  git fetch --no-tags origin "+refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF" ||
    { echo "silent-undo: UNKNOWN, cannot fetch base $BASE_REF"; exit 1; }
fi
python3 "$here/../../lint/check_silent_undo.py" --repo "$root" --upstream "origin/$BASE_REF" --head "${HEAD_SHA:-HEAD}" --pr-body-env PR_BODY --strict
