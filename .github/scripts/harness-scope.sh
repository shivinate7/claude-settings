#!/usr/bin/env bash
# Decides which mutation harnesses a run needs. Writes guard=<bool> and sweep=<bool> to
# $GITHUB_OUTPUT. Fails safe: every harness runs unless the diff was read and shows neither
# harness's code changed. Inputs (env): EVENT, BASE_SHA, BEFORE_SHA.
set -u
guard=true
sweep=true
range=""
# An empty BASE_SHA (pull_request) or an empty or all-zeros BEFORE_SHA (push, new branch)
# leaves range empty, so both harnesses run.
case "$EVENT" in
  pull_request) [ -n "$BASE_SHA" ] && range="$BASE_SHA...HEAD" ;;
  push) [ -n "${BEFORE_SHA//0/}" ] && range="$BEFORE_SHA...HEAD" ;;
esac
# --no-renames lists the old path of a rename too, so a move out of a trigger path counts.
if [ -n "$range" ] && files=$(git diff --name-only --no-renames "$range" 2>/dev/null); then
  guard=false
  sweep=false
  # Guard harness code: everything in hooks/ (guard, its suite, the harness, config_watch and
  # its suite), this script and the workflow (a break in the scope logic must run the
  # harnesses), and lint/_transcript.py (no harness imports it; kept because the ruling
  # names it). The guard and its suites import only the standard library; mutate_guard.py
  # imports hooks/mutate_shared.py.
  grep -Eq '^(hooks/|lint/_transcript\.py$|\.github/scripts/harness-scope\.sh$|\.github/workflows/gates\.yml$)' <<< "$files" && guard=true
  # Janitor harness code: janitor/, guard.py (janitor imports it), mutate_shared.py (the
  # harness imports it), settings.json (the session-end suite reads it), this script and
  # the workflow.
  grep -Eq '^(janitor/|hooks/guard\.py$|hooks/mutate_shared\.py$|settings\.json$|\.github/scripts/harness-scope\.sh$|\.github/workflows/gates\.yml$)' <<< "$files" && sweep=true
fi
echo "harness scope: event=$EVENT range=${range:-none} guard=$guard sweep=$sweep"
echo "guard=$guard" >> "$GITHUB_OUTPUT"
echo "sweep=$sweep" >> "$GITHUB_OUTPUT"
