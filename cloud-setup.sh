#!/usr/bin/env bash
# Cloud environment setup script. It installs this repo's agents, hooks and skills before Claude
# Code starts, so ~/.claude/agents/builder.md exists before the first agent spawn (decision
# agent-model-cap). It never fails setup: it always exits 0 and prints one verdict line.
#
#   Cloud setup script:  the paste block in the environment's settings fetches this file.
set -u

REPO="shivinate7/claude-settings"
RAW="${CLAUDE_SETTINGS_RAW:-https://raw.githubusercontent.com/${REPO}/main}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
CAP="${CLAUDE_SETTINGS_SETUP_CAP:-240}"

verdict() { printf 'claude-settings setup: %s\n' "$*"; }

# True when git origin URL $1 names $REPO on github.com, in https, ssh or scp form. A copy of
# origin_matches_repo in install.sh, because install.sh cannot be sourced: it runs on load.
origin_is_repo() {
  o=$(printf '%s' "$1" | tr -d '\r\n')
  o="${o%/}"
  o="${o%.git}"
  case "$o" in
    *://*@github.com/"$REPO"|*://github.com/"$REPO"|*://*@github.com:*/"$REPO"|*://github.com:*/"$REPO") return 0 ;;
    *@github.com:"$REPO") return 0 ;;
  esac
  return 1
}

# Print the install.sh of a local checkout under the search roots, the first whose origin matches.
local_install_sh() {
  for root in ${CLAUDE_SETTINGS_SEARCH_ROOTS:-/home/user /root "$HOME"}; do
    [ -d "$root" ] || continue
    for child in "$root"/*; do
      [ -f "$child/install.sh" ] || continue
      origin=$(git -C "$child" config --get remote.origin.url 2>/dev/null) || continue
      origin_is_repo "$origin" && { printf '%s' "$child/install.sh"; return 0; }
    done
  done
  return 1
}

main() {
  [ "$(uname -s)" = "Linux" ] || return 0

  # install.sh moves a checkout to main mid-run, so it runs from a temp copy, never in place.
  tmp=$(mktemp 2>/dev/null) || { verdict "no source (mktemp failed)"; return 0; }
  trap 'rm -f "$tmp"' EXIT

  have=0
  if curl -fsS --max-time 20 "$RAW/install.sh" -o "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
    have=1
  else
    src=$(local_install_sh) && cp "$src" "$tmp" 2>/dev/null && [ -s "$tmp" ] && have=1
  fi
  if [ "$have" -ne 1 ]; then
    verdict "no source: GitHub is down, or a private repo is not under the environment's Repositories"
    return 0
  fi

  rc=0
  if command -v timeout >/dev/null 2>&1; then
    timeout "$CAP" bash "$tmp" --cloud </dev/null || rc=$?
  else
    bash "$tmp" --cloud </dev/null || rc=$?
  fi

  if [ -f "$CLAUDE_DIR/agents/builder.md" ]; then
    verdict "installed"
  elif [ "$rc" -eq 124 ]; then
    verdict "timed out after ${CAP}s"
  else
    verdict "exit $rc"
  fi
  return 0
}

main "$@"; exit 0
