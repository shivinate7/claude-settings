#!/usr/bin/env bash
# Decides which mutation harnesses a run needs. Writes guard=<bool> and sweep=<bool> to
# $GITHUB_OUTPUT. Fails safe: every harness runs unless the diff was read and shows neither
# harness's code changed. Inputs (env): EVENT, BASE_SHA, BEFORE_SHA.
set -u
guard=true
sweep=true
range=""
case "$EVENT" in
  pull_request) range="$BASE_SHA...HEAD" ;;
  # An all-zeros BEFORE_SHA is a new-branch push: leave range empty, so both harnesses run.
  push) case "$BEFORE_SHA" in *[!0]*) range="$BEFORE_SHA...HEAD" ;; esac ;;
esac
if [ -n "$range" ] && files=$(git diff --name-only "$range" 2>/dev/null); then
  guard=false
  sweep=false
  # Guard harness code: everything in hooks/ (guard, its suite, the harness, config_watch and
  # its suite) plus lint/_transcript.py. The guard and its suites import only the standard
  # library; mutate_guard.py imports hooks/mutate_shared.py.
  grep -Eq '^(hooks/|lint/_transcript\.py$)' <<< "$files" && guard=true
  # Janitor harness code: janitor/, guard.py (janitor imports it), mutate_shared.py (the
  # harness imports it) and settings.json (the session-end suite reads it).
  grep -Eq '^(janitor/|hooks/guard\.py$|hooks/mutate_shared\.py$|settings\.json$)' <<< "$files" && sweep=true
fi
echo "harness scope: event=$EVENT range=${range:-none} guard=$guard sweep=$sweep"
echo "guard=$guard" >> "$GITHUB_OUTPUT"
echo "sweep=$sweep" >> "$GITHUB_OUTPUT"
