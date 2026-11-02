#!/usr/bin/env bash
# Open the issue titled $1, or comment on it when one is already open. Body is $2.
# One open issue collects every repeat, so a week of red nights is one issue. Needs GH_TOKEN.
# Prints nothing on success. A failed read or write prints `unknown` and a warning, and exits 0.
title="$1"; body="$2"; repo="${GITHUB_REPOSITORY:?}"
unknown() { echo unknown; echo "::warning::issue: $1"; exit 0; }
open="$(gh issue list --repo "$repo" --state open --search "\"$title\" in:title" \
  --json number,title --jq "[.[] | select(.title == \"$title\")][0].number // empty")" \
  || unknown "gh issue list failed"
if [ -n "$open" ]; then gh issue comment "$open" --repo "$repo" --body "$body" >&2 || unknown "gh issue comment failed"
else gh issue create --repo "$repo" --title "$title" --body "$body" >&2 || unknown "gh issue create failed"; fi
