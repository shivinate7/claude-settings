#!/usr/bin/env bash
# The composite action's own logic, pulled out of action.yml so it can be run and tested
# directly (test_action.sh does exactly that, against a throwaway git remote) rather than only
# ever exercised inside a GitHub Actions runner.
#
# MODE picks one of two runs. Default "stamp".
#   check  run `stamp.mjs --check`. Needs only STAMP_JS and CONFIG. No default branch, no gate, no
#          commit, no push, so it runs with `contents: read` on any branch or pull request.
#          BASE is optional. When set, it passes through as `--base`. When empty, it is left out.
#   stamp  the env vars below. All are required except MAX_ATTEMPTS and REGENERATE_COMMAND.
#
#   REF                e.g. "refs/heads/main" ($GITHUB_REF)
#   DEFAULT_BRANCH     e.g. "main"
#   STAMP_JS           path to stamp.mjs
#   CONFIG             path to the stamp config, passed through to stamp.mjs
#   REGENERATE_COMMAND optional, empty means skip. Runs after --stamp, before the gate, in
#                      the same commit. It is the caller's own generator (a refs/pointer pass,
#                      an index table). Each repo keeps its own generator. This only times it.
#   GATE_COMMAND       shell command that must pass on the stamped tree before it is pushed
#   SUBJECT_TEMPLATE   commit subject template, "{ids}" expands to the stamped ids
#   BOT_NAME, BOT_EMAIL
#   STAMP_TOKEN        the push credential. Only `git fetch` and `git push` receive it.
#   MAX_ATTEMPTS       default 3
set -euo pipefail

# THE TOKEN NEVER REACHES CALLER CODE. Copy it into a shell variable that is not exported, then
# drop it from the environment, so no child (regenerate, gate, stamp.mjs, git commit) inherits it.
# It goes to git only through `git_auth`, as per-command env: never argv, never .git/config.
# Limit: the gate runs as this user, so a determined attacker can still read process memory.
# Full isolation needs a separate push job.
stamp_token="${STAMP_TOKEN:-}"
unset STAMP_TOKEN

MODE="${MODE:-stamp}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-3}"

case "$MODE" in
  check)
    # BASE, when set, names the base. Else the engine picks it: origin/$GITHUB_BASE_REF on a pull
    # request, else origin/<defaultBranch>. Its exit code is this run's verdict.
    exec node "$STAMP_JS" --check ${BASE:+--base "$BASE"} --config "$CONFIG"
    ;;
  stamp) ;;
  *)
    echo "stamp REFUSES: mode is '$MODE'. Use 'stamp' or 'check'."
    exit 2
    ;;
esac

if [ -z "$stamp_token" ]; then
  echo "stamp REFUSES: mode 'stamp' needs a token. Nothing was written."
  exit 2
fi

# A credential that checkout persisted into .git/config is readable by the caller's code, and it
# would make the token input pointless. Refuse and name the remedy.
if git config --local --get-regexp '^(http\..*extraheader|credential\..*)$' >/dev/null 2>&1 \
   || git config --local --get remote.origin.url | grep -q '://[^/]*@'; then
  echo "stamp REFUSES: .git/config holds a credential for the remote. Set 'persist-credentials: false' on actions/checkout."
  exit 2
fi

git_auth_header="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$stamp_token" | base64 | tr -d '\n')"
unset stamp_token
git_auth() {
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="http.${GITHUB_SERVER_URL:-https://github.com}/.extraheader" \
    GIT_CONFIG_VALUE_0="$git_auth_header" git "$@"
}

# An empty gate passes every tree. The input is optional only so that mode "check" can omit it.
if [ -z "${GATE_COMMAND:-}" ]; then
  echo "stamp REFUSES: mode 'stamp' needs a gate-command. Nothing was written."
  exit 2
fi

# Refuse off the default branch. This action writes to the branch it runs on, and running it
# anywhere else would let two branches claim the same number. That collision is the one the rule
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

  # THE CALLER'S OWN GENERATOR, IN THE SAME COMMIT. A repo that regenerates a refs block, an
  # index table, or a lookup file from its records must keep doing so. Adopting this action
  # must change nothing else about the tree. It runs on the stamped tree, before the gate, so
  # the gate checks what the commit will actually carry.
  if [ -n "${REGENERATE_COMMAND:-}" ]; then
    if ! bash -c "$REGENERATE_COMMAND"; then
      echo "stamp: the regenerate command failed. Not pushing. Entries stay pending."
      rm -f "$OUT"
      exit 1
    fi
  fi

  # THE GATE RUNS ON THE STAMPED TREE, BEFORE THE PUSH. A push made with the workflow's own token
  # starts no other workflow, so nothing else will check this tree. Red here means no push, and
  # the run fails with the entries still pending, which the next stamp run reads and retries.
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

  if git_auth push -q; then
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
  # the new HEAD without re-running the gate on the result. That leaves a pushed tree that
  # nothing ever checked.
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  git_auth fetch -q origin "$BRANCH"
  git reset -q --hard "origin/$BRANCH"
  attempt=$((attempt + 1))
done
