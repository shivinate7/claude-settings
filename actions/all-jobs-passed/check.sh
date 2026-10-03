#!/usr/bin/env bash
# Fails unless NEEDS (toJSON(needs)) is non-empty and every job's result is success.
# failure, cancelled and skipped all fail: a skipped required job must not read as green.
set -euo pipefail
echo "$NEEDS" | jq -r 'to_entries[] | "\(.key): \(.value.result)"'
echo "$NEEDS" | jq -e 'length > 0 and all(.[]; .result == "success")' >/dev/null
