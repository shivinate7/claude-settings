#!/usr/bin/env bash
# The one wake for a CI alarm on a push to main. It posts one comment on the earliest merged pull request
# into main that holds commit SHA, which wakes the batch runner that watches that pull request. It opens no issue.
# Needs REPO (owner/name), SHA, KEY, TEXT (the comment text) and GH_TOKEN. The env check below covers the
# first four; a missing GH_TOKEN fails loud at the first gh call, the pulls read.
# KEY is caller-chosen and names one alarm: the cap alarm (unbuilt, restart-plan R16) should use `cap:<run id>:<attempt>`. A caller with two
# alarm kinds on one run id must pick a distinct KEY per kind, or the second alarm's text is dropped.
# The caller's token needs pull-requests: read for the pulls and comments reads, and pull-requests: write
# for the comment post.
# The hidden marker `<!-- main-alarm:KEY -->` in the comment is the memory: a pull request that already
# holds it gets no second comment. WAKE_DRY=1 (the test seam) prints the body and posts nothing.
# A commit with no pull request merged into main has nobody to wake: the message goes to GITHUB_STEP_SUMMARY when
# set, else stderr, and the exit is non-zero so the alarm job ends red.
set -uo pipefail

for v in REPO SHA KEY TEXT; do
  [ -n "${!v:-}" ] || { echo "wake.sh: $v is not set" >&2; exit 2; }
done
# KEY lands inside an HTML comment that is later matched as plain text, so it stays free of quotes,
# newlines and a comment closer.
if [[ ! "$KEY" =~ ^[A-Za-z0-9._:-]+$ || "$KEY" == *"-->"* ]]; then
  echo "wake.sh: KEY may hold only letters, digits and . _ : - and never -->" >&2
  exit 2
fi

fail() {
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then printf '%s\n' "$1" >> "$GITHUB_STEP_SUMMARY"; else printf '%s\n' "$1" >&2; fi
  exit 1
}

# Only a pull request into main counts: one into another branch can hold the commit without putting it on
# main. Of those, the earliest merge put the commit on main; a later one only carried it on.
pr="$(gh api "repos/$REPO/commits/$SHA/pulls" \
  --jq '[.[] | select(.merged_at != null and .base.ref == "main")] | sort_by(.merged_at) | .[0].number // empty')" \
  || fail "CI alarm $KEY: the read of the pull requests for commit ${SHA:0:7} failed, so nobody was woken."
[ -n "$pr" ] || fail "CI alarm $KEY: commit ${SHA:0:7} has no pull request merged into main, so there is nobody to wake and no issue is opened. Text: $TEXT"

marker="<!-- main-alarm:$KEY -->"
# Every page is read: the marker may sit on a late page of a long thread.
seen="$(gh api --paginate "repos/$REPO/issues/$pr/comments?per_page=100" --jq '.[].body')" \
  || fail "CI alarm $KEY: the read of the comments on pull request $pr failed, so nobody was woken."
if grep -qF -- "$marker" <<<"$seen"; then
  echo "CI alarm $KEY is already on pull request $pr: no comment."
  exit 0
fi

body="$marker
$TEXT"
if [ "${WAKE_DRY:-}" = 1 ]; then printf '%s\n' "$body"; exit 0; fi
gh pr comment "$pr" --repo "$REPO" --body "$body" \
  || fail "CI alarm $KEY: the comment on pull request $pr was not posted, so nobody was woken."
