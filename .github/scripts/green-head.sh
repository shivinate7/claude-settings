#!/usr/bin/env bash
# Prints the head sha of a pull request's newest earlier fully green `checks` run, for ci-scope.sh (env GREEN_HEAD).
# Prints one line. The line is the sha only when the newest earlier run (event pull_request, a head sha other than HEAD_SHA)
# is completed, concluded success, and its jobs `scope` and `all-jobs-passed` concluded success too. In every other case the
# line is empty: no earlier run, a red, running or cancelled newest run (an older green run never counts when a newer run is
# not green), a skipped scope job (a draft run), a gh error or malformed JSON. Unknown is never green. Always exits 0.
# Inputs (env): REPO (owner/name), PR (number), HEAD_SHA, GH_TOKEN (read by gh). Cost: one runs read and one jobs read per run.
# Fork pull requests list no pull_requests on their runs, so they print an empty line.
set -u
none() { printf '\n'; exit 0; }
[ -n "${REPO:-}" ] && [ -n "${PR:-}" ] && [ -n "${HEAD_SHA:-}" ] || none
command -v gh >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 || none

runs=$(gh api "repos/$REPO/actions/workflows/checks.yml/runs?event=pull_request&per_page=100" 2>/dev/null) || none
# The newest earlier run of this pull request, whatever its state: only its own conclusion can make it green.
pick=$(printf '%s' "$runs" | jq -r --arg pr "$PR" --arg head "$HEAD_SHA" '
  [.workflow_runs[]
   | select(.event == "pull_request" and .head_sha != $head and any(.pull_requests[]?; (.number | tostring) == $pr))]
  | sort_by(.created_at) | reverse | .[0] // empty
  | select(.status == "completed" and .conclusion == "success")
  | "\(.id) \(.head_sha)"' 2>/dev/null) || none
run_id=${pick%% *}
sha=${pick#* }
case "$run_id" in ''|*[!0-9]*) none ;; esac
case "$sha" in ''|*[!0-9a-f]*) none ;; esac

jobs=$(gh api "repos/$REPO/actions/runs/$run_id/jobs?per_page=100" 2>/dev/null) || none
ok=$(printf '%s' "$jobs" | jq -r '
  [.jobs[] | select(.name == "scope" and .conclusion == "success")] as $s
  | [.jobs[] | select(.name == "all-jobs-passed" and .conclusion == "success")] as $p
  | ($s | length) == 1 and ($p | length) == 1' 2>/dev/null) || none
[ "$ok" = true ] || none
printf '%s\n' "$sha"
