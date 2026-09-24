#!/usr/bin/env bash
# The composite action's own logic, pulled out of action.yml so it can be run and tested
# directly (test_action.sh does exactly that, against a throwaway git remote) rather than only
# ever exercised inside a GitHub Actions runner.
#
# Env vars, all required except MAX_ATTEMPTS:
#   REF              e.g. "refs/heads/main" ($GITHUB_REF)
#   DEFAULT_BRANCH   e.g. "main"
#   STAMP_JS         path to stamp.mjs
#   CONFIG           path to the stamp config, passed through to stamp.mjs
#   GATE_COMMAND     shell command that must pass on the stamped tree before it is pushed
#   SUBJECT_TEMPLATE commit subject template, "{ids}" expands to the stamped ids
#   BOT_NAME, BOT_EMAIL
#   MAX_ATTEMPTS     default 3
set -euo pipefail

MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"

# Refuse off the default branch. This action writes to the branch it runs on, and running it
# anywhere else would let two branches claim the same number — the exact collision the mandate
# exists to prevent.
if [ "$REF" != "refs/heads/$DEFAULT_BRANCH" ]; then
  echo "stamp REFUSES: ref is '$REF', not the default branch ('refs/heads/$DEFAULT_BRANCH')."
  exit 1
fi

attempt=1
while :; do
  echo "stamp: attempt $attempt of $MAX_ATTEMPTS"

  OUT="$(mktemp)"
  if ! node "$STAMP_JS" --stamp --config "$CONFIG" | tee "$OUT"; then
    echo "stamp: refused. Nothing was written."
    rm -f "$OUT"
    exit 1
  fi

  if git diff --quiet && git diff --cached --quiet; then
    echo "stamp: nothing pending. Nothing to push."
    rm -f "$OUT"
    exit 0
  fi

  # THE GATE RUNS ON THE STAMPED TREE, BEFORE THE PUSH — the same reason q_max's stamp.yml runs
  # its three gate commands itself (D-478, the stamp checks its own tree): a push made with the
  # workflow's own token starts no other workflow, so nothing else will check this tree. Red
  # here means no push, and the run fails with the entries still pending, which the next stamp
  # run reads and retries.
  if ! bash -c "$GATE_COMMAND"; then
    echo "stamp: the gate failed on the stamped tree. Not pushing. Entries stay pending."
    rm -f "$OUT"
    exit 1
  fi

  IDS="$(sed -n 's/^stamped \([^ ]*\).*/\1/p' "$OUT" | tr '\n' ' ' | sed 's/ $//')"
  rm -f "$OUT"
  SUBJECT="${SUBJECT_TEMPLATE/\{ids\}/$IDS}"

  git config user.name "$BOT_NAME"
  git config user.email "$BOT_EMAIL"
  git add -A
  git commit -q -m "$SUBJECT"

  if git push -q; then
    echo "stamp: pushed. $SUBJECT"
    exit 0
  fi

  echo "stamp: push rejected — the default branch moved."
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "stamp: gave up after $MAX_ATTEMPTS attempts. The commit made it no further than this runner; the entries stay pending on the remote, and the next push's stamp run reads that tree."
    exit 1
  fi
  # RE-DERIVE, NEVER REBASE. `--stamp` is a pure function of the tree, so the safe way to answer
  # "main moved" is to throw the local commit away and run the whole stamp-gate-commit cycle
  # again against the tree as it stands now. A rebase would replay our stamp commit on top of
  # the new HEAD without re-running the gate on the result — the exact hole q_max's own
  # stamp.yml measured (D-478): a rebased tree that nothing ever checked.
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  git fetch -q origin "$BRANCH"
  git reset -q --hard "origin/$BRANCH"
  attempt=$((attempt + 1))
done
