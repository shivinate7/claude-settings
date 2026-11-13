#!/usr/bin/env bash
# Runs the ruling-kind lint on the caller's checkout (the current directory) against the pull
# request base in BASE_REF. An empty BASE_REF is not a pull request: skip, by design.
# Fail closed: a base that cannot be read or diffed is red. CI=true makes the lint itself
# exit 1 on a git diff failure; the lint is told so here, so a local run behaves the same.
# The base is the local origin/$BASE_REF when it exists. Fetch only when it is missing: a caller
# checkout with persist-credentials: false has no credentials, so a fetch of it would fail.
# A Home: rule:<id> resolves against the caller's CLAUDE.md and the action's own (same sha).
set -u
here="$(cd "$(dirname "$0")" && pwd)"
action_root="$here/../.."
if [ -z "${BASE_REF:-}" ]; then
  echo "ruling-kind: no pull request base, skipped"
  exit 0
fi
RECORDS_DIR="${RECORDS_DIR-}"  # empty: the lint reads the folder from lint/layout.json
case "$RECORDS_DIR" in
  *..*|/*) echo "ruling-kind: records-dir must be a folder inside the checkout, not '$RECORDS_DIR'"; exit 1 ;;
esac
root="$(git rev-parse --show-toplevel)" || { echo "ruling-kind: UNKNOWN, not a git checkout"; exit 1; }
if ! git rev-parse --verify -q "refs/remotes/origin/$BASE_REF" > /dev/null; then
  git fetch --no-tags origin "+refs/heads/$BASE_REF:refs/remotes/origin/$BASE_REF" ||
    { echo "ruling-kind: UNKNOWN, cannot fetch base $BASE_REF"; exit 1; }
fi
# The file list is lint/rule_audit.py RULE_FILES, the one home, read from the action's own checkout.
rule_list="$(python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); import rule_audit; print(chr(10).join(p.replace(chr(92), "/") for p in rule_audit.RULE_FILES))' "$action_root/lint")" ||
  { echo "ruling-kind: UNKNOWN, cannot read RULE_FILES from lint/rule_audit.py"; exit 1; }
rules=()
for d in "$root" "$action_root"; do
  while IFS= read -r f; do rules+=(--rules-file "$d/$f"); done <<< "$rule_list"
done
if [ -z "$RECORDS_DIR" ]; then
  # The layout's folder, passed as --dir so the lint still refuses a folder that does not exist.
  RECORDS_DIR="$(python3 "$here/../../lint/layout.py" path "$root" decisions)" ||
    { echo "ruling-kind: UNKNOWN, cannot read the layout"; exit 1; }
fi
CI=true python3 "$here/../../lint/check_ruling_kind.py" --root "$root" --dir "$RECORDS_DIR" --base "origin/$BASE_REF" "${rules[@]}"
