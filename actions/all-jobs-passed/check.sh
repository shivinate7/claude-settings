#!/usr/bin/env bash
# Fails unless NEEDS (toJSON(needs)) is non-empty and every job's result is success.
# failure, cancelled and skipped all fail: a skipped required job must not read as green.
# SCOPE_SKIPS, when set, is one JSON object {job: [scope flag, ...]}. A skipped job passes only when it is a key of that object,
# its flag list is not empty, the scope job succeeded, and each listed flag in needs.scope.outputs is exactly "false".
# Unset or empty, no skip passes. A SCOPE_SKIPS that is not JSON fails the check (jq exits non-zero under set -e).
set -euo pipefail
echo "$NEEDS" | jq -r 'to_entries[] | "\(.key): \(.value.result)"'
if [ -z "${SCOPE_SKIPS:-}" ]; then
  echo "$NEEDS" | jq -e 'length > 0 and all(.[]; .result == "success")' >/dev/null
else
  echo "$NEEDS" | jq -e --argjson skips "$SCOPE_SKIPS" '
    . as $needs
    | def gated($name): ($skips | type) == "object" and ($skips[$name] | type) == "array" and ($skips[$name] | length) > 0
        and $needs.scope.result == "success"
        and all($skips[$name][]; . as $flag | $needs.scope.outputs[$flag] == "false");
    length > 0 and all(to_entries[]; .value.result == "success" or (.value.result == "skipped" and gated(.key)))' >/dev/null
fi
