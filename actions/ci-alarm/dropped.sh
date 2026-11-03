#!/usr/bin/env bash
# Alarm on an open pull request whose head commit has no real CHECK run: a dropped `pull_request` event
# leaves the required check never started, and nothing says so. Lists open pull requests (one read per 100), skips
# drafts and any updated 300 s ago or less, reads the check runs of the head sha for CHECK (a skipped run
# counts as absent, since a draft's run skips every job), then reads the PR's comments for the marker
# `<!-- dropped-start-alarm:<sha> -->`. With no run and no marker it posts one comment holding the marker and
# the remedy. Nothing is cancelled, re-run or pushed, and no empty commit is suggested. Env: GH_TOKEN,
# GITHUB_REPOSITORY, CHECK (default all-jobs-passed, DRAFT_SKIP_CHECK in merge/merge.py), NOW (epoch
# seconds, default the clock). Exit 0 always. Prints "green" (nothing posted), "red" (a comment posted) or
# "unknown"; a failed read or write is unknown, never red, and nothing is posted after it.
set -o pipefail
repo="${GITHUB_REPOSITORY:?}"
# The default equals DRAFT_SKIP_CHECK in merge/merge.py; test_action.sh pins the two equal.
check="${CHECK:-all-jobs-passed}"
now="${NOW:-$(date -u +%s)}"
unknown() { echo unknown; echo "::warning::ci-alarm dropped-start: $1"; exit 0; }
[[ "$now" =~ ^[0-9]+$ ]] || unknown "NOW is not an epoch in seconds"
pulls="$(gh api "repos/$repo/pulls?state=open&per_page=100" --paginate)" || unknown "gh api pulls failed"
# Ready pull requests whose last update is over 300 s old: number and head sha.
ready="$(jq -r -s --argjson now "$now" 'if all(.[]; type == "array") then .[][]
    | select((.draft | not) and ($now - (.updated_at | fromdateiso8601) > 300))
    | [.number, .head.sha] | @tsv else error("not a list") end' <<<"$pulls" 2>/dev/null)" \
  || unknown "gh api pulls gave no list of pull requests"
flagged=0
while IFS=$'\t' read -r number sha; do
  [ -n "$number" ] || continue
  real="$(gh api "repos/$repo/commits/$sha/check-runs?check_name=$check" \
    --jq '[.check_runs[] | select(.conclusion != "skipped")] | length')" || unknown "gh api check-runs failed for #$number"
  [[ "$real" =~ ^[0-9]+$ ]] || unknown "check-runs of #$number gave no count"
  [ "$real" = 0 ] || continue
  marker="<!-- dropped-start-alarm:$sha -->"
  bodies="$(gh api "repos/$repo/issues/$number/comments?per_page=100" --paginate --jq '.[].body')" \
    || unknown "gh api comments failed for #$number"
  if grep -qF -- "$marker" <<<"$bodies"; then continue; fi
  body="$marker
No \`$check\` run has started for \`${sha:0:7}\`, five minutes after the last update. GitHub may have dropped the pull request event. Mark the pull request a draft and ready again (\`gh pr ready $number --undo\`, then \`gh pr ready $number\`)."
  # Not issue.sh: that one dedupes by issue title; this one dedupes per head sha on a PR, by the marker.
  gh api --method POST "repos/$repo/issues/$number/comments" -f body="$body" >/dev/null \
    || unknown "gh api comment write failed for #$number"
  flagged=1
done <<<"$ready"
if [ "$flagged" = 1 ]; then echo red; else echo green; fi
