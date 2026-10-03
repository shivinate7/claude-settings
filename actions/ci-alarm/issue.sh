#!/usr/bin/env bash
# Open the issue titled $1, or comment on it when one is already open. Body is $2.
# One open issue collects every repeat, so a week of red nights is one issue. Needs GH_TOKEN.
set -euo pipefail
title="$1"; body="$2"; repo="${GITHUB_REPOSITORY:?}"
open="$(gh issue list --repo "$repo" --state open --search "\"$title\" in:title" \
  --json number,title --jq "[.[] | select(.title == \"$title\")][0].number // empty")"
if [ -n "$open" ]; then gh issue comment "$open" --repo "$repo" --body "$body"
else gh issue create --repo "$repo" --title "$title" --body "$body"; fi
